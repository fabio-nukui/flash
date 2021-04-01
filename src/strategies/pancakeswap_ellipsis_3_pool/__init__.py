import logging
import time
from itertools import permutations

from web3 import Web3
from web3._utils.filters import Filter

import configs
from core.entities import Token, TokenAmount
from dex.curve import EllipsisClient
from dex.uniswap_v2 import PancakeswapClient
from tools import cache, optimization

MAX_HOPS = 1
MIN_CONFIRMATIONS = 5
POOL_NAME = '3pool'
GAS_COST_USD = 2

# Optimization paramenters
INITIAL_VALUE = 100  # Initial value to estimate best trade
INCREMENT = 0.0001  # Increment to estimate derivatives in optimization
TOLERANCE = 0.01  # Tolerance to stop optimization
MAX_ITERATIONS = 100


def _is_close(a, b, rtol=1e-4):
    """Clecks if a and b are close by relative tolerance tol"""
    return abs(a - b) / (a + b) / 2 < rtol


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
            f'{self.__class__.__name__}({self.token_1.symbol}->'
            f'{self.token_2.symbol}->{self.token_1.symbol})'
        )

    def _estimate_result_int(self, amount_2_int: int) -> int:
        amount_2 = TokenAmount(self.token_2, amount_2_int)
        return self._estimate_result(amount_2).amount

    def _estimate_result(self, amount_2: TokenAmount) -> TokenAmount:
        trade_cake = self.cake_client.dex.best_trade_exact_out(self.token_1, amount_2, MAX_HOPS)
        trade_eps = self.eps_client.dex.best_trade_exact_in(
            amount_2, self.token_1, pools=[POOL_NAME])

        return trade_eps.amount_out - trade_cake.amount_in

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
            self._estimate_result_int,
            amount_2_initial.amount,
            int(INCREMENT * 10 ** self.token_2.decimals),
            int(TOLERANCE * 10 ** self.token_2.decimals),
            MAX_ITERATIONS,
        )

        self.amount_2 = TokenAmount(self.token_2, int_amount_2)
        self.estimated_result = TokenAmount(self.token_1, int_result)

    def get_net_result(self):
        # TODO: subtract real gas costs
        gas_costs_in_token_wei = TokenAmount(
            self.token_1, GAS_COST_USD * 10 ** self.token_1.decimals)
        return self.estimated_result - gas_costs_in_token_wei

    def execute(self):
        raise NotImplementedError
        transaction_hash = self.trigger_contract()
        self.mark_running(transaction_hash)

    def trigger_contract(self):
        raise NotImplementedError

    def mark_running(self, transaction_hash: str):
        self._is_running = True
        self._transaction_hash = transaction_hash

    def _reset(self):
        self._is_running = False
        self._transaction_hash = ''

    def is_running(self, current_block: int) -> bool:
        if not self._is_running:
            return False
        receipt = self.web3.eth.getTransactionReceipt(self.transaction_hash)
        if receipt.status == 0:
            logging.info(f'Transaction {self.transaction_hash} failed')
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
                logging.warning(f'More than one block passed since last iteration ({len(entries)})')
            return web3.eth.block_number
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
        best_arbitrage = max(arb_pair, key=lambda x: x.estimated_result)
        if best_arbitrage.get_net_result() > 0:
            logging.info('Arbitrage opportunity found')
            best_arbitrage.execute()
