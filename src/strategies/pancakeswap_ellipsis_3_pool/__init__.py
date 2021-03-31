import logging
import time
from itertools import permutations

from web3 import Web3
from web3._utils.filters import Filter

import configs
from core.entities import Token, TokenAmount
from dex.curve import CurvePool, EllipsisClient
from dex.uniswap_v2 import PancakeswapClient
from tools import cache


INITIAL_AMOUNT = 10_000  # Initial amount to estimate best trade amount
MAX_HOPS = 2
MIN_CONFIRMATIONS = 4


class TradeCandidate:
    def __init__(self, token_in: Token, token_out: Token, web3: Web3):
        self.token_in = token_in
        self.token_out = token_out
        self.web3 = web3

        self._is_running = False
        self._transaction_hash = ''

    def __repr__(self):
        return f'{self.__class__.__name__}({self.token_in.symbol}->{self.token_out.symbol})'

    def mark_running(self, transaction_hash: str):
        self._is_running = True
        self._transaction_hash = transaction_hash

    def _reset(self):
        self._is_running = False
        self._transaction_hash = ''

    def is_running(self, current_block: int):
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
            self._reset()
            return False


def wait_for_new_block(block_filter: Filter):
    while True:
        entries = block_filter.get_new_entries()
        if len(entries) > 0:
            if len(entries) > 1:
                logging.warning(f'More than one block passed since last iteration ({len(entries)})')
            return
        time.sleep(configs.POLL_INTERVAL)


def get_candidates(tokens: list[Token], web3: Web3) -> list[TradeCandidate]:
    return [
        TradeCandidate(token_in, token_out, web3)
        for token_in, token_out in permutations(tokens, 2)
    ]


def get_best_trade(
    trade_candidate: TradeCandidate,
    cake_client: PancakeswapClient,
    pool: CurvePool
):
    amount_wei = INITIAL_AMOUNT * 10 ** trade_candidate.token_in.decimals
    amount_in_eps = TokenAmount(trade_candidate.token_in, amount_wei)
    amount_out_eps = pool.get_amount_out(amount_in_eps, trade_candidate.token_out)
    amount_in_cake = cake_client.dex.best_trade_exact_out(
        trade_candidate.token_in,
        amount_out_eps,
        MAX_HOPS
    )


def run_trade(trade, web3: Web3):
    pass


def run(web3: Web3):
    """Search for arbitrate oportunity using flash swap starting from pancakeswap to
    Ellipsis's 3pool and back (USDT / USDC / BUSD)"""
    cake_client = PancakeswapClient(configs.ADDRESS, configs.PRIVATE_KEY, web3)
    eps_client = EllipsisClient(configs.ADDRESS, configs.PRIVATE_KEY, web3)
    pool = eps_client.dex.pools['3pool']
    candidates = get_candidates(pool.tokens, web3)

    block_filter = web3.eth.filter('latest')
    while True:
        wait_for_new_block(block_filter)
        cache.clear_caches()
        for trade_candidate in candidates:
            if trade_candidate.is_running:
                continue
            trade = get_best_trade(trade_candidate, cake_client, pool)
            if trade.result > 0:
                transaction_hash = run_trade(trade, web3)
                trade_candidate.mark_running(transaction_hash)
