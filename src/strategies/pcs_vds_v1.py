# Pancakeswap (PCS) x ValueDefiSwap (VDS)

import json
import logging
import time
from itertools import permutations
from typing import Iterable, Union

from web3 import Web3
from web3._utils.filters import Filter
from web3.contract import Contract
from web3.exceptions import TransactionNotFound

import configs
import tools
from core import Token, TokenAmount, TradePairs
from dex import PancakeswapDex, ValueDefiSwapDex
from exceptions import InsufficientLiquidity

# Strategy parameters
MAX_HOPS_FIRST_DEX = 2
MAX_HOPS_SECOND_DEX = 1
MIN_CONFIRMATIONS = 1
MIN_ESTIMATED_PROFIT = 1

# Gas-related parameters
HOP_PENALTY = 0.1  # Penaly on trades with extra hops to account for higher gas fees
GAS_COST = 170_000
GAS_SHARE_OF_PROFIT = 0.20
MAX_GAS_MULTIPLIER = 3

# Optimization parameters
INITIAL_VALUE = 1  # Initial value in USD to estimate best trade
INCREMENT = 0.001  # Increment to estimate derivatives in optimization
TOLERANCE_USD = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100

# Created with notebooks/2021-04-12-pcs_vds_v1.ipynb
ADDRESS_FILEPATH = 'addresses/strategies/pcs_eps_3pool_v1.json'
CONTRACT_DATA_FILEPATH = ''

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

        self._is_running = False
        self._transaction_hash = ''
        self._gas_price = 0
        self.estimated_net_result_usd = 0.0
        self._insufficient_liquidity = False

    def __repr__(self):
        return (
            f'{self.__class__.__name__}'
            f'({self.token_first.symbol}->{self.token_last.symbol}->{self.token_first.symbol}, '
            f'first_dex={self.first_dex}, '
            f'est_result=US${self.estimated_net_result_usd:,.2f})'
        )

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
            self._update_estimate()
        except InsufficientLiquidity:
            logging.info(f'Insufficient liquidity for {self}, removing it from next iterations')
            self._insufficient_liquidity = True

    def _update_estimate(self):
        usd_price_token_last = tools.price.get_price_usd(self.token_last, self.pairs)
        amount_last_initial = TokenAmount(
            self.token_last,
            int(INITIAL_VALUE / usd_price_token_last * 10 ** self.token_last.decimals)
        )
        result_initial = self._estimate_result(amount_last_initial)
        if result_initial < 0:
            # If gross result is negative even with small amount gross, skip optimization
            self.amount_last = amount_last_initial
            self.estimated_result = result_initial
            return

        int_amount_last, int_result = tools.optimization.optimizer_second_order(
            func=self._estimate_result_int,
            x0=amount_last_initial.amount,
            dx=int(INCREMENT * 10 ** self.token_last.decimals / usd_price_token_last),
            tol=int(TOLERANCE_USD * 10 ** self.token_last.decimals / usd_price_token_last),
            max_iter=MAX_ITERATIONS,
        )
        if int_amount_last < 0:  # Fail-safe in case optimizer returns negative inputs
            return
        self.amount_last = TokenAmount(self.token_last, int_amount_last)
        self.estimated_result = TokenAmount(self.token_first, int_result)
        self.first_trade, self.second_trade = self._get_arbitrage_trades(self.amount_last)
        self._set_gas_and_net_result()

    def _set_gas_and_net_result(self):
        token_usd_price = tools.price.get_price_usd(
            self.estimated_result.token,
            self.pairs,
            self.web3,
        )
        gross_result_usd = self.estimated_result.amount_in_units * token_usd_price

        gas_cost_usd = tools.price.get_gas_cost_usd(GAS_COST)
        gas_premium = GAS_SHARE_OF_PROFIT * gross_result_usd / gas_cost_usd
        gas_premium = max(gas_premium, 1)

        self._gas_price = int(tools.price.get_gas_price() * gas_premium)
        self.estimated_net_result_usd = gross_result_usd - gas_cost_usd * gas_premium

    def _get_contract_function(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapVdsFirst

    def _get_mid_path_argument(self):
        if isinstance(self.first_dex, PancakeswapDex):
            vdf_pair_address = self.second_trade.route.pairs[0]
            return [vdf_pair_address] + self.first_trade.route.tokens[1:-1]
        return self.first_trade.route.tokens[1:-1]

    def execute(self):
        log.info(f'Estimated profit: {self.estimated_net_result_usd}')
        log.info(f'Trades: {self.trade_cake}; {self.trade_eps}')
        log.info(f'Gas price: {self._gas_price / 10 ** 9:,.1f} Gwei')

        transaction_hash = tools.contracts.sign_and_send_transaction(
            func=self._get_contract_function(),
            tokenFirst=self.token_first.address,
            tokenLast=self.token_last.address,
            amountLast=self.amount_last.amount,
            midPath=self._get_mid_path_argument(),
            max_gas_=GAS_COST * MAX_GAS_MULTIPLIER,
            gas_price_=self._gas_price,
        )
        self._is_running = True
        self._transaction_hash = transaction_hash
        log.info(f'Sent transaction with hash {transaction_hash}')

    def _reset(self):
        self._is_running = False
        self._transaction_hash = ''
        self.amount_last = TokenAmount(self.token_last)
        self.estimated_result = TokenAmount(self.token_first)
        self.first_trade = None
        self.second_trade = None
        self._gas_price = 0
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
            log.info(f'Transaction {self._transaction_hash} failed')
            self._reset()
            return False
        elif current_block - receipt.blockNumber < (MIN_CONFIRMATIONS - 1):
            return True
        # Minimum amount of confimations passed
        log.info(
            f'Transaction {self._transaction_hash} succeeded. '
            f'(Estimated profit: {self.estimated_net_result_usd})'
        )
        self._reset()
        return False


def get_latest_block(block_filter: Filter, web3: Web3) -> int:
    while True:
        entries = block_filter.get_new_entries()
        if len(entries) > 0:
            if len(entries) > 1:
                log.warning(f'More than one block passed since last iteration ({len(entries)})')
            block_number = web3.eth.block_number
            log.debug(f'New block: {block_number}')
            return block_number
        time.sleep(configs.POLL_INTERVAL)


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
        pcs_dex = PancakeswapDex(pairs_addresses=addresses['pcs_dex'])
        vds_dex = ValueDefiSwapDex(pairs_addresses=addresses['vds_dex'])
    contract = tools.contracts.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        ArbitragePair(**params, contract=contract, web3=web3)
        for params in get_arbitrage_params(pcs_dex, vds_dex)
    ]
    block_filter = web3.eth.filter('latest')
    while True:
        latest_block = get_latest_block(block_filter, web3)
        tools.cache.clear_caches()
        if any([pair.is_running(latest_block) for pair in arbitrage_pairs]):
            continue
        for arb_pair in arbitrage_pairs:
            arb_pair.update_estimate()
        best_arbitrage = max(arbitrage_pairs, key=lambda x: x.estimated_net_result_usd)
        if best_arbitrage.estimated_net_result_usd > MIN_ESTIMATED_PROFIT:
            log.info('Arbitrage opportunity found')
            best_arbitrage.execute()
