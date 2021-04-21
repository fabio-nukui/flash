# Pancakeswap (PCS) x ValueDefiSwap (VDS)

import json
import logging
from itertools import permutations
from typing import Iterable, Union

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound

import tools
import configs
from core import Token, TokenAmount, TradePairs
from dex import PancakeswapDex, ValueDefiSwapDex
from exceptions import InsufficientLiquidity

# Strategy parameters
MAX_HOPS_FIRST_DEX = 2
MAX_HOPS_SECOND_DEX = 1
MIN_CONFIRMATIONS = 1
MIN_ESTIMATED_PROFIT = 1

# Gas-related parameters; data from notebooks/pcs_vds_analysis.ipynb (2021-04-20)
GAS_COST_PCS_FIRST_CHI_OFF = 226_230.2
GAS_COST_VDS_FIRST_CHI_OFF = 209_520.3
GAS_COST_PCS_FIRST_CHI_ON = 156_279.7
GAS_COST_VDS_FIRST_CHI_ON = 139_586.4
GAS_INCREASE_WITH_HOP = 0.266831606034439
GAS_SHARE_OF_PROFIT = 0.26
HOP_PENALTY = GAS_SHARE_OF_PROFIT * GAS_INCREASE_WITH_HOP  # TODO: Simulate more than one hop configuration per arbitrage pair  # noqa: E501
MAX_GAS_MULTIPLIER = 2

# Optimization parameters
INITIAL_VALUE = 1  # Initial value in USD to estimate best trade
INCREMENT = 0.001  # Increment to estimate derivatives in optimization
TOLERANCE_USD = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100

# Created with notebooks/2021-04-12-pcs_vds_v1.ipynb
ADDRESS_FILEPATH = 'addresses/strategies/pcs_vds_v1.json'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsVdsV1.json'

log = logging.getLogger(__name__)

Dex = Union[PancakeswapDex, ValueDefiSwapDex]


class ArbitragePair:
    def __init__(
        self,
        token_first: Token,
        token_last: Token,
        first_dex: Dex,
        second_dex: Dex,
        contract: Contract,
        web3: Web3
    ):
        self.token_first = token_first
        self.token_last = token_last
        self.first_dex = first_dex
        self.second_dex = second_dex
        self.contract = contract
        self.web3 = web3
        self.pairs = self.first_dex.pairs + self.second_dex.pairs

        self.amount_last = TokenAmount(token_last)
        self.estimated_result = TokenAmount(token_first)
        self.first_trade: TradePairs = None
        self.second_trade: TradePairs = None

        self._is_set = False
        self._is_running = False
        self._transaction_hash = ''
        self.gas_price = 0
        self.gas_cost = 0
        self.estimated_gross_result_usd = 0.0
        self.estimated_net_result_usd = 0.0
        self._insufficient_liquidity = False

    def __repr__(self):
        return (
            f'{self.__class__.__name__}'
            f'({self.token_first.symbol}->{self.token_last.symbol}->{self.token_first.symbol}, '
            f'first_dex={self.first_dex}, '
            f'est_result=US${self.estimated_net_result_usd:,.2f})'
        )

    def _get_gas_cost(self, estimated_gross_result_usd: float) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pairs) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops
        if isinstance(self.first_dex, PancakeswapDex):
            gas_cost_chi_off = int(GAS_COST_PCS_FIRST_CHI_OFF * gas_cost_multiplier)
        else:
            gas_cost_chi_off = int(GAS_COST_VDS_FIRST_CHI_OFF * gas_cost_multiplier)
        min_tx_cost = tools.price.get_gas_cost_native_tokens(gas_cost_chi_off)

        price_native_token_usd = tools.price.get_price_usd_native_token(self.web3)
        gross_result_native_token = estimated_gross_result_usd / price_native_token_usd

        if gross_result_native_token * GAS_SHARE_OF_PROFIT < 2 * min_tx_cost:
            return gas_cost_chi_off

        if isinstance(self.first_dex, PancakeswapDex):
            return int(GAS_COST_PCS_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_VDS_FIRST_CHI_ON * gas_cost_multiplier)

    def _estimate_result_int(self, amount_last_int: int) -> int:
        amount_last = TokenAmount(self.token_last, amount_last_int)
        return self._estimate_result(amount_last).amount

    def _estimate_result(self, amount_last: TokenAmount) -> TokenAmount:
        first_trade, second_trade = self._get_arbitrage_trades(amount_last)
        return second_trade.amount_out - first_trade.amount_in

    def _get_arbitrage_trades(self, amount_last: TokenAmount) -> tuple[TradePairs, TradePairs]:
        first_trade = self.first_dex.best_trade_exact_out(
            self.token_first, amount_last, MAX_HOPS_FIRST_DEX, HOP_PENALTY)
        second_trade = self.second_dex.best_trade_exact_in(
            amount_last, self.token_first, MAX_HOPS_SECOND_DEX, HOP_PENALTY)
        return first_trade, second_trade

    def update_estimate(self):
        if self._insufficient_liquidity:
            return
        try:
            if self._is_set:
                self._reset()
            self._update_estimate()
        except InsufficientLiquidity:
            logging.info(f'Insufficient liquidity for {self}, removing it from next iterations')
            self._reset()
            self._insufficient_liquidity = True

    def _update_estimate(self):
        usd_price_token_last = tools.price.get_price_usd(self.token_last, self.pairs)
        amount_last_initial = TokenAmount(
            self.token_last,
            int(INITIAL_VALUE / usd_price_token_last * 10 ** self.token_last.decimals)
        )
        result_initial = self._estimate_result(amount_last_initial)
        if result_initial < 0:
            # If gross result is negative even with small amount, skip optimization
            return
        try:
            int_amount_last, int_result = tools.optimization.optimizer_second_order(
                func=self._estimate_result_int,
                x0=amount_last_initial.amount,
                dx=int(INCREMENT * 10 ** self.token_last.decimals / usd_price_token_last),
                tol=int(TOLERANCE_USD * 10 ** self.token_last.decimals / usd_price_token_last),
                max_iter=MAX_ITERATIONS,
            )
        except Exception as e:
            log.info(f'{self}: Error during optimization: {e!r}')
            log.debug('Error: ', exc_info=True)
            return
        if int_amount_last < 0:  # Fail-safe in case optimizer returns negative inputs
            return
        amount_last = TokenAmount(self.token_last, int_amount_last)
        estimated_result = TokenAmount(self.token_first, int_result)
        self._set_arbitrage_params(amount_last, estimated_result)

    def _set_arbitrage_params(self, amount_last: TokenAmount, estimated_result: TokenAmount):
        self._is_set = True
        self.amount_last = amount_last
        self.estimated_result = estimated_result
        self.first_trade, self.second_trade = self._get_arbitrage_trades(amount_last)

        token_usd_price = tools.price.get_price_usd(estimated_result.token, self.pairs, self.web3)
        self.estimated_gross_result_usd = estimated_result.amount_in_units * token_usd_price
        self.gas_cost = self._get_gas_cost(self.estimated_gross_result_usd)

        gas_cost_usd = tools.price.get_gas_cost_usd(self.gas_cost)
        gas_premium = GAS_SHARE_OF_PROFIT * self.estimated_gross_result_usd / gas_cost_usd
        gas_premium = max(gas_premium, 1)

        self.gas_price = int(tools.price.get_gas_price() * gas_premium)
        self.estimated_net_result_usd = self.estimated_gross_result_usd - gas_cost_usd * gas_premium

    def _get_contract_function(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapVdsFirst

    def _get_path_argument(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return [
                self.second_trade.route.pairs[0].address,
                *(t.address for t in self.first_trade.route.tokens)
            ]
        return [
            self.token_first.address,
            self.token_last.address,
            *(p.address for p in self.first_trade.route.pairs)
        ]

    def execute(self):
        transaction_hash = tools.contracts.sign_and_send_contract_transaction(
            func=self._get_contract_function(),
            path=self._get_path_argument(),
            amountLast=self.amount_last.amount,
            max_gas_=int(self.gas_cost * MAX_GAS_MULTIPLIER),
            gas_price_=self.gas_price,
        )
        self._is_running = True
        self._transaction_hash = transaction_hash
        log.info(f'Sent transaction with hash {transaction_hash}')
        log.info(
            f'Trades: {self.first_dex}:{self.first_trade}; {self.second_dex}:{self.second_trade}')
        est_tx_cost = self.gas_price * self.gas_cost / 10 ** tools.price.get_native_token_decimals()
        log.info(json.dumps({
            'tx_hash': transaction_hash,
            'estimated_net_result_usd': self.estimated_net_result_usd,
            'estimated_gross_result_usd': self.estimated_gross_result_usd,
            'gas_price': self.gas_price,
            'est_tx_cost': est_tx_cost,
            'token_first_symbol': self.token_first.symbol,
            'token_last_symbol': self.token_last.symbol,
            'token_last_amount': self.amount_last.amount,
            'n_hops': len(self.first_trade.route.pairs),
        }))
        reserves = {
            pair: pair.reserves
            for pair in self.first_trade.route.pairs + self.second_trade.route.pairs
        }
        log.debug(f'Reserves: {reserves}')

    def _reset(self):
        self._is_set = False
        self._is_running = False
        self._transaction_hash = ''
        self.amount_last = TokenAmount(self.token_last)
        self.estimated_result = TokenAmount(self.token_first)
        self.first_trade = None
        self.second_trade = None
        self.gas_price = 0
        self.gas_cost = 0
        self.estimated_gross_result_usd = 0.0
        self.estimated_net_result_usd = 0.0

    def is_running(self, current_block: int) -> bool:
        if not self._is_running:
            return False
        try:
            receipt = self.web3.eth.getTransactionReceipt(self._transaction_hash)
        except TransactionNotFound:
            log.info(f'Transaction {self._transaction_hash} not found in node')
            return True
        if receipt.status == 0:
            log.info(f'Transaction {self._transaction_hash} failed (gas_used={receipt.gasUsed})')
            return False
        elif current_block - receipt.blockNumber < (MIN_CONFIRMATIONS - 1):
            return True
        # Minimum amount of confimations passed
        log.info(
            f'Transaction {self._transaction_hash} succeeded (gas_used={receipt.gasUsed}). '
            f'(Estimated profit: {self.estimated_net_result_usd})'
        )
        return False


def get_arbitrage_params(
    pcs_dex: PancakeswapDex,
    vds_dex: ValueDefiSwapDex,
) -> Iterable[dict]:
    for dex_0, dex_1 in permutations([pcs_dex, vds_dex]):
        for pair in dex_1.pairs:
            for token_first, token_last in permutations(pair.tokens):
                yield {
                    'token_first': token_first,
                    'token_last': token_last,
                    'first_dex': dex_0,
                    'second_dex': dex_1,
                }


def run():
    web3 = tools.w3.get_web3(verbose=True)
    with open(ADDRESS_FILEPATH) as f:
        addresses = json.load(f)
        pcs_dex = PancakeswapDex(pairs_addresses=addresses['pcs_dex'], web3=web3)
        vds_dex = ValueDefiSwapDex(pairs_addresses=addresses['vds_dex'], web3=web3)
    contract = tools.contracts.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        ArbitragePair(**params, contract=contract, web3=web3)
        for params in get_arbitrage_params(pcs_dex, vds_dex)
    ]
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        if any([pair.is_running(block_number) for pair in arbitrage_pairs]):
            continue
        for arb_pair in arbitrage_pairs:
            arb_pair.update_estimate()
        best_arbitrage = max(arbitrage_pairs, key=lambda x: x.estimated_net_result_usd)
        if best_arbitrage.estimated_net_result_usd > MIN_ESTIMATED_PROFIT:
            log.info(f'Arbitrage opportunity found on block {block_number}')
            if (current_block := web3.eth.block_number) != block_number:
                raise Exception(
                    'Latest block advanced since beggining of iteration: '
                    f'{block_number=} vs {current_block=}'
                )
            best_arbitrage.execute()
