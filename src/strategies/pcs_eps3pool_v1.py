"""Pancakeswap (pcs) x Elipsis 3pool (eps3pool)"""
import json
import logging
from itertools import permutations

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound

import tools
from core import Token, TokenAmount, TradePairs
from dex.curve import CurveTrade, EllipsisDex
from dex.uniswap_v2 import PancakeswapDex

MAX_HOPS = 1
MIN_CONFIRMATIONS = 1
GAS_COST = 170_000
GAS_SHARE_OF_PROFIT = 0.4
MIN_ESTIMATED_PROFIT = 1

# Optimization paramenters
INITIAL_VALUE = 100  # Initial value to estimate best trade
INCREMENT = 0.0001  # Increment to estimate derivatives in optimization
TOLERANCE = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100

# Use V1 contract for now, as it has lower gas costs
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PancakeswapEllipsis3PoolV1B.json'
ADDRESS_FILEPATH = 'addresses/strategies/pcs_eps_3pool_v1.json'

log = logging.getLogger(__name__)


class ArbitragePair:
    def __init__(
        self,
        token_first: Token,
        token_last: Token,
        cake_dex: PancakeswapDex,
        eps_dex: EllipsisDex,
        contract: Contract,
        web3: Web3
    ):
        self.token_first = token_first
        self.token_last = token_last
        self.cake_dex = cake_dex
        self.eps_dex = eps_dex
        self.contract = contract
        self.web3 = web3

        self.amount_last = TokenAmount(token_last)
        self.estimated_result = TokenAmount(token_first)
        self.trade_cake: TradePairs = None
        self.trade_eps: CurveTrade = None

        self._is_set = False
        self._is_running = False
        self._transaction_hash = ''
        self._gas_price = 0
        self.estimated_net_result_usd = 0.0

    def __repr__(self):
        return (
            f'{self.__class__.__name__}'
            f'({self.token_first.symbol}->{self.token_last.symbol}->{self.token_first.symbol}, '
            f'estimated_net_result_usd={self.estimated_net_result_usd:,.2f})'
        )

    def _estimate_result_int(self, amount_last_int: int) -> int:
        amount_last = TokenAmount(self.token_last, amount_last_int)
        return self._estimate_result(amount_last).amount

    def _estimate_result(self, amount_last: TokenAmount) -> TokenAmount:
        trade_cake, trade_eps = self._get_arbitrage_trades(amount_last)
        return trade_eps.amount_out - trade_cake.amount_in

    def _get_arbitrage_trades(self, amount_last: TokenAmount) -> tuple[TradePairs, CurveTrade]:
        trade_cake = self.cake_dex.best_trade_exact_out(self.token_first, amount_last, MAX_HOPS)
        trade_eps = self.eps_dex.best_trade_exact_in(amount_last, self.token_first)
        return trade_cake, trade_eps

    def update_estimate(self) -> TokenAmount:
        if self._is_set:
            self._reset()
        amount_last_initial = TokenAmount(
            self.token_last, INITIAL_VALUE * 10 ** self.token_last.decimals)
        result_initial = self._estimate_result(amount_last_initial)
        if result_initial < 0:
            # If gross result is negative even with small amount gross, skip optimization
            self.amount_last = amount_last_initial
            self.estimated_result = result_initial
            return

        int_amount_last, int_result = tools.optimization.optimizer_second_order(
            func=self._estimate_result_int,
            x0=amount_last_initial.amount,
            dx=round(INCREMENT * 10 ** self.token_last.decimals),
            tol=round(TOLERANCE * 10 ** self.token_last.decimals),
            max_iter=MAX_ITERATIONS,
        )
        if int_amount_last < 0:  # Fail-safe in case optimizer returns negative inputs
            return
        amount_last = TokenAmount(self.token_last, int_amount_last)
        estimated_result = TokenAmount(self.token_first, int_result)
        self._set_arbitrage_params(amount_last, estimated_result)

    def _set_arbitrage_params(self, amount_last: TokenAmount, estimated_result: TokenAmount):
        self._is_set = True
        self.amount_last = amount_last
        self.estimated_result = estimated_result
        self.trade_cake, self.trade_eps = self._get_arbitrage_trades(amount_last)

        token_usd_price = tools.price.get_chainlink_price_usd(estimated_result.token)
        gross_result_usd = estimated_result.amount_in_units * token_usd_price

        gas_cost_usd = tools.price.get_gas_cost_usd(GAS_COST)
        gas_premium = GAS_SHARE_OF_PROFIT * gross_result_usd / gas_cost_usd
        gas_premium = max(gas_premium, 1)

        self._gas_price = round(tools.price.get_gas_price() * gas_premium)
        self.estimated_net_result_usd = gross_result_usd - gas_cost_usd * gas_premium

    def execute(self):
        log.info(f'Estimated profit: {self.estimated_net_result_usd}')
        log.info(f'Trades: {self.trade_cake}; {self.trade_eps}')
        log.info(f'Gas price: {self._gas_price / 10 ** 9:,.1f} Gwei')

        transaction_hash = tools.transaction.sign_and_send_contract_tx(
            func=self.contract.functions.triggerFlashSwap,
            token0=self.token_first.address,
            token1=self.token_last.address,
            amount1=self.amount_last.amount,
            max_gas_=GAS_COST * 2,
            gas_price_=self._gas_price,
        )
        # transaction_hash = tools.transaction.sign_and_send_contract_tx(
        #     self.contract.functions.triggerFlashSwap,
        #     path=[t.address for t in self.trade_cake.route.tokens],
        #     amountLast=self.amount_last.amount,
        #     max_gas_=GAS_COST * 2,
        #     gas_price_=self._gas_price,
        # )
        self._is_running = True
        self._transaction_hash = transaction_hash
        log.info(f'Sent transaction with hash {transaction_hash}')

    def _reset(self):
        self._is_set = False
        self._is_running = False
        self._transaction_hash = ''
        self.amount_last = TokenAmount(self.token_last)
        self.estimated_result = TokenAmount(self.token_first)
        self.trade_cake = None
        self.trade_eps = None
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
            return False
        elif current_block - receipt.blockNumber < (MIN_CONFIRMATIONS - 1):
            return True
        # Minimum amount of confimations passed
        log.info(
            f'Transaction {self._transaction_hash} succeeded. '
            f'(Estimated profit: {self.estimated_net_result_usd})'
        )
        return False


def run():
    """Search for arbitrage oportunity using flash swap starting from pancakeswap to
    Ellipsis's 3pool and back (USDT / USDC / BUSD)"""
    web3 = tools.w3.get_web3(verbose=True)
    addresses = json.load(open(ADDRESS_FILEPATH))

    cake_dex = PancakeswapDex(tokens=addresses['cake_dex'])
    eps_dex = EllipsisDex(pool_names=addresses['eps_dex'])

    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        ArbitragePair(token_first, token_last, cake_dex, eps_dex, contract, web3)
        for token_first, token_last in permutations(eps_dex.tokens, 2)
    ]
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks(update_block_config=True):
        tools.cache.clear_caches()
        if any([pair.is_running(block_number) for pair in arbitrage_pairs]):
            continue
        for arb_pair in arbitrage_pairs:
            arb_pair.update_estimate()
        best_arbitrage = max(arbitrage_pairs, key=lambda x: x.estimated_net_result_usd)
        if best_arbitrage.estimated_net_result_usd > MIN_ESTIMATED_PROFIT:
            log.info(f'Arbitrage opportunity found on block {block_number}')
            best_arbitrage.execute()
