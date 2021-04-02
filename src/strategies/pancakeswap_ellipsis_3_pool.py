import time
from itertools import permutations

from web3 import Web3
from web3._utils.filters import Filter

import configs
from core.entities import Token, TokenAmount
from dex.curve import CurveTrade, EllipsisClient
from dex.uniswap_v2 import PancakeswapClient, UniV2Trade
from tools import cache, optimization, price
from tools.logger import log

MAX_HOPS = 1
MIN_CONFIRMATIONS = 5
POOL_NAME = '3pool'
GAS_COST = 1_000_000  # TODO: replace with real contract's gas costs
GAS_PREMIUM_FACTOR = 2  # TODO: Calculate premium via % failed transactions

# Optimization paramenters
INITIAL_VALUE = 100  # Initial value to estimate best trade
INCREMENT = 0.0001  # Increment to estimate derivatives in optimization
TOLERANCE = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100


class ArbitragePair:
    def __init__(
        self,
        token_1: Token,
        token_2: Token,
        cake_client: PancakeswapClient,
        eps_client: EllipsisClient,
        web3: Web3,
    ):
        self.token_1 = token_1
        self.token_2 = token_2
        self.cake_client = cake_client
        self.eps_client = eps_client
        self.web3 = web3

        self.amount_2 = TokenAmount(token_2)
        self.estimated_result = TokenAmount(token_1)

        self._is_running = False
        self._transaction_hash = ''

    def __repr__(self):
        return (
            f'{self.__class__.__name__}({self.token_1.symbol}->{self.token_2.symbol}->'
            f'{self.token_1.symbol}, estimated_net_result_usd={self.estimated_net_result_usd:,.2f})'
        )

    @property
    def estimated_net_result_usd(self) -> float:
        if self.estimated_result.is_empty():
            return 0.0
        token_usd_price = price.get_chainlink_price_usd(
            self.estimated_result.token.symbol, self.web3)

        gross_result_usd = self.estimated_result.amount_in_units * token_usd_price
        gas_cost_usd = price.get_gas_cost_usd(GAS_COST * GAS_PREMIUM_FACTOR, self.web3)

        return gross_result_usd - gas_cost_usd

    def _estimate_result_int(self, amount_2_int: int) -> int:
        amount_2 = TokenAmount(self.token_2, amount_2_int)
        return self._estimate_result(amount_2).amount

    def _estimate_result(self, amount_2: TokenAmount) -> TokenAmount:
        trade_cake = self.cake_client.dex.best_trade_exact_out(self.token_1, amount_2, MAX_HOPS)
        trade_eps = self.eps_client.dex.best_trade_exact_in(
            amount_2, self.token_1, pools=[POOL_NAME])

        return trade_eps.amount_out - trade_cake.amount_in

    def _get_arbitrage_params(self) -> tuple[UniV2Trade, CurveTrade]:
        trade_cake = self.cake_client.dex.best_trade_exact_out(
            self.token_1, self.amount_2, MAX_HOPS)
        trade_eps = self.eps_client.dex.best_trade_exact_in(
            self.amount_2, self.token_1, pools=[POOL_NAME])
        return trade_cake, trade_eps

    def update_estimate(self) -> TokenAmount:
        amount_2_initial = TokenAmount(
            self.token_2, int(INITIAL_VALUE * 10 ** self.token_2.decimals))

        result_initial = self._estimate_result(amount_2_initial)
        if result_initial < 0:
            # If gross result is negative even with small amount gross, skip optimization
            self.amount_2 = amount_2_initial
            self.estimated_result = result_initial
            return

        int_amount_2, int_result = optimization.optimizer_second_order(
            func=self._estimate_result_int,
            x0=amount_2_initial.amount,
            dx=int(INCREMENT * 10 ** self.token_2.decimals),
            tol=int(TOLERANCE * 10 ** self.token_2.decimals),
            max_iter=MAX_ITERATIONS,
        )

        self.amount_2 = TokenAmount(self.token_2, int_amount_2)
        self.estimated_result = TokenAmount(self.token_1, int_result)

    def execute(self):
        log.info(f'Estimated profit: {self.estimated_net_result_usd}')
        log.info(f'Arbitrage params: {self._get_arbitrage_params()}')
        return
        raise NotImplementedError
        transaction_hash = self.trigger_contract()
        self.mark_running(transaction_hash)

    def trigger_contract(self) -> str:
        return '0x1234'
        raise NotImplementedError

    def mark_running(self, transaction_hash: str):
        self._is_running = True
        self._transaction_hash = transaction_hash

    def _reset(self):
        self._is_running = False
        self._transaction_hash = ''

    def is_running(self, current_block: int) -> bool:
        return False
        raise NotImplementedError
        if not self._is_running:
            return False
        receipt = self.web3.eth.getTransactionReceipt(self._transaction_hash)
        if receipt.status == 0:
            log.info(f'Transaction {self._transaction_hash} failed')
            self._reset()
            return False
        elif current_block - receipt.blockNumber < MIN_CONFIRMATIONS:
            return True
        else:
            # Minimum amount of confimations passed
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


def get_arbitrage_pairs(
    tokens: list[Token],
    cake_client: PancakeswapClient,
    eps_client: EllipsisClient,
    web3: Web3
) -> list[ArbitragePair]:
    return [
        ArbitragePair(token_in, token_out, cake_client, eps_client, web3)
        for token_in, token_out in permutations(tokens, 2)
    ]


def run(web3: Web3):
    """Search for arbitrate oportunity using flash swap starting from pancakeswap to
    Ellipsis's 3pool and back (USDT / USDC / BUSD)"""
    cake_client = PancakeswapClient(configs.ADDRESS, configs.PRIVATE_KEY, web3)
    eps_client = EllipsisClient(configs.ADDRESS, configs.PRIVATE_KEY, web3)
    tokens = eps_client.dex.pools[POOL_NAME].tokens
    arbitrage_pairs = get_arbitrage_pairs(tokens, cake_client, eps_client, web3)

    block_filter = web3.eth.filter('latest')
    while True:
        latest_block = get_latest_block(block_filter, web3)
        cache.clear_caches()
        if any(arb_pair.is_running(latest_block) for arb_pair in arbitrage_pairs):
            continue
        for arb_pair in arbitrage_pairs:
            arb_pair.update_estimate()
        best_arbitrage = max(arbitrage_pairs, key=lambda x: x.estimated_net_result_usd)
        if best_arbitrage.estimated_net_result_usd > 0:
            log.info('Arbitrage opportunity found')
            best_arbitrage.execute()
