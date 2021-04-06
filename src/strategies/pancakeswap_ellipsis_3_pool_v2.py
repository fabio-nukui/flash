import json
import time
from concurrent import futures
from itertools import permutations

from web3 import Web3
from web3._utils.filters import Filter
from web3.contract import Contract
from web3.exceptions import TransactionNotFound

import configs
from core.entities import Token, TokenAmount
from dex.curve import CurveTrade, EllipsisDex
from dex.uniswap_v2 import PancakeswapDex, UniV2Trade
from tools import cache, contracts, optimization, price, web3_tools
from tools.logger import log

MAX_HOPS = 2
MIN_CONFIRMATIONS = 3
POOL_NAME = '3pool'
GAS_COST = 260_000
GAS_PREMIUM_FACTOR = 5  # TODO: Calculate premium via % failed transactions

# Optimization paramenters
INITIAL_VALUE = 100  # Initial value to estimate best trade
INCREMENT = 0.0001  # Increment to estimate derivatives in optimization
TOLERANCE = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100

CONTRACT_DATA_FILEPATH = 'deployed_contracts/PancakeswapEllipsis3PoolV2.json'
ADDRESS_FILEPATH = 'addresses/strategies/pancakeswap_ellipsis_3_pool_v2.json'


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
        self.trade_cake: UniV2Trade = None
        self.trade_eps: CurveTrade = None

        self._is_running = False
        self._transaction_hash = ''

    def __repr__(self):
        return (
            f'{self.__class__.__name__}'
            f'({self.token_first.symbol}->{self.token_last.symbol}->{self.token_first.symbol}, '
            f'estimated_net_result_usd={self.estimated_net_result_usd:,.2f})'
        )

    @property
    def estimated_net_result_usd(self) -> float:
        if self.estimated_result.is_empty():
            return 0.0
        token_usd_price = price.get_chainlink_price_usd(self.estimated_result.token.symbol)

        gross_result_usd = self.estimated_result.amount_in_units * token_usd_price
        gas_cost_usd = price.get_gas_cost_usd(GAS_COST * GAS_PREMIUM_FACTOR)

        return gross_result_usd - gas_cost_usd

    def _estimate_result_int(self, amount_last_int: int) -> int:
        amount_last = TokenAmount(self.token_last, amount_last_int)
        return self._estimate_result(amount_last).amount

    def _estimate_result(self, amount_last: TokenAmount) -> TokenAmount:
        trade_cake, trade_eps = self._get_arbitrage_trades(amount_last)
        return trade_eps.amount_out - trade_cake.amount_in

    def _get_arbitrage_trades(self, amount_last: TokenAmount) -> tuple[UniV2Trade, CurveTrade]:
        with futures.ProcessPoolExecutor(2) as pool:
            fut_trade_cake = pool.submit(
                self.cake_dex.best_trade_exact_out, self.token_first, amount_last, MAX_HOPS)
            fut_trade_eps = pool.submit(
                self.eps_dex.best_trade_exact_in, amount_last, self.token_first, pools=[POOL_NAME])
        return fut_trade_cake.result(), fut_trade_eps.result()

    def update_estimate(self) -> TokenAmount:
        amount_last_initial = TokenAmount(
            self.token_last, int(INITIAL_VALUE * 10 ** self.token_last.decimals))
        result_initial = self._estimate_result(amount_last_initial)
        if result_initial < 0:
            # If gross result is negative even with small amount gross, skip optimization
            self.amount_last = amount_last_initial
            self.estimated_result = result_initial
            return

        int_amount_last, int_result = optimization.optimizer_second_order(
            func=self._estimate_result_int,
            x0=amount_last_initial.amount,
            dx=int(INCREMENT * 10 ** self.token_last.decimals),
            tol=int(TOLERANCE * 10 ** self.token_last.decimals),
            max_iter=MAX_ITERATIONS,
        )

        if int_amount_last < 0:
            return

        self.amount_last = TokenAmount(self.token_last, int_amount_last)
        self.estimated_result = TokenAmount(self.token_first, int_result)
        self.trade_cake, self.trade_eps = self._get_arbitrage_trades(self.amount_last)

    def execute(self):
        log.info(f'Estimated profit: {self.estimated_net_result_usd}')
        log.info(f'Trades: {self.trade_cake}; {self.trade_eps}')
        log.info(
            f'Reserves: cake={self.trade_cake.route.pairs[0].reserves}; '
            f'eps={self.trade_eps.pool.reserves}'
        )

        transaction_hash = contracts.sign_and_send_transaction(
            self.contract.functions.triggerFlashSwap,
            path=[t.address for t in self.trade_cake.route.tokens],
            amountLast=self.amount_last.amount,
        )
        self._is_running = True
        self._transaction_hash = transaction_hash
        log.info(f'Sent transaction with hash {transaction_hash}')

    def _reset(self):
        self._is_running = False
        self._transaction_hash = ''
        self.amount_last = TokenAmount(self.token_last)
        self.estimated_result = TokenAmount(self.token_first)
        self.trade_cake = None
        self.trade_eps = None

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
        elif current_block - receipt.blockNumber < MIN_CONFIRMATIONS:
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


def run():
    """Search for arbitrate oportunity using flash swap starting from pancakeswap to
    Ellipsis's 3pool and back (USDT / USDC / BUSD)"""
    web3 = web3_tools.get_web3(verbose=True)
    tokens = EllipsisDex(web3).pools[POOL_NAME].tokens
    with open(ADDRESS_FILEPATH) as f:
        cake_dex_tokens = json.load(f)['cake_dex']
        cake_dex = PancakeswapDex(tokens=cake_dex_tokens)
    eps_dex = EllipsisDex()
    contract = contracts.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        ArbitragePair(token_first, token_last, cake_dex, eps_dex, contract, web3)
        for token_first, token_last in permutations(tokens, 2)
    ]
    block_filter = web3.eth.filter('latest')
    while True:
        latest_block = get_latest_block(block_filter, web3)
        cache.clear_caches()
        if any([pair.is_running(latest_block) for pair in arbitrage_pairs]):
            continue
        with futures.ProcessPoolExecutor(len(arbitrage_pairs)) as pool:
            for arb_pair in arbitrage_pairs:
                pool.submit(arb_pair.update_estimate)
        best_arbitrage = max(arbitrage_pairs, key=lambda x: x.estimated_net_result_usd)
        if best_arbitrage.estimated_net_result_usd > 0:
            log.info('Arbitrage opportunity found')
            best_arbitrage.execute()
