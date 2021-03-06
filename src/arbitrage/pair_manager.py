from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import sys
import time
from copy import copy
from enum import Enum
from itertools import product, permutations
from typing import Iterable, Type, Union

from web3 import Web3

import tools
from core import LiquidityPool, Route, RoutePairs, Token, TokenAmount
from dex import DexProtocol
from exceptions import InsufficientLiquidity

from .arbitrage_pair_v1 import ArbitragePairV1, TxStatus

log = logging.getLogger(__name__)

PathLike = Union[bytes, str, os.PathLike]

POOLS_FILE = 'pools.json'
REMOVED_POOLS_FILE = 'pools_removed.json'
REMOVED_POOLS_BACKUP_FILE = 'pools_removed_BAK.json'
ARBITRAGE_PAIR_SUMMARY_FILENAME = 'summary.json'
ARBITRAGE_PAIR_SUMMARY_BACKUP_FILENAME = 'summary_BAK.json'

DEFAULT_MIN_PROFITABILITY = 2.0
DEFAULT_MAX_HOPS_DEX_1 = 2
DEFAULT_MIN_POOL_SUCCESS_RATE = 0.2
DEFAULT_MIN_POOL_SUCCESS_RATE_SAMPLE_SIZE = 20
DEFAULT_MAX_POOL_REPEATED_FAILURES = 5
DEFAULT_MAX_TOTAL_REPEATED_FAILURES = 10
MIN_AMOUNT_OUT_USD = 1.0
MAX_TRANSACTIONS_STORE_PER_PAIR = 1000

# Disable if testing transaction raises message with any of the following messages
PAT_ERROR_REMOVE_POOL = re.compile('K|TransferHelper|TRANSFER_FAILED')


class PoolStatus(Enum):
    enabled = 'enabled'
    disabled = 'disabled'
    untested = 'untested'


class ManagedPair:
    def __init__(
        self,
        arb: ArbitragePairV1,
        pools: list[ManagedPool],
        data_directory: pathlib.Path,
    ):
        self.arb = arb
        self.pools = {pool for pool in pools if pool.lp in arb.pools}
        self.data_directory = data_directory

        self._change_summary_file = False
        self._new_transactions = False
        self._flag_disabled = False
        self.n_successes = 0
        self.n_failures = 0
        self.transactions: list[dict] = []

        self.route_0_addresses = [p.address for p in self.arb.route_0.pools]
        self.route_1_addresses = [p.address for p in self.arb.route_1.pools]

        addresses = [
            arb.token_first.address,
            arb.token_last.address,
            *self.route_1_addresses,  # route_1_addresses need to be first for compatibility
            *self.route_0_addresses,
        ]
        self.hash_ = Web3.sha3(text=''.join(addresses)).hex()[:42]
        self.data_directory = data_directory / 'arb_pairs' / self.hash_
        self.summary_filepath = self.data_directory / ARBITRAGE_PAIR_SUMMARY_FILENAME
        self.summary_backup_filepath = self.data_directory / ARBITRAGE_PAIR_SUMMARY_BACKUP_FILENAME
        self.transactions_directory = self.data_directory / 'tx'
        self.transactions_directory.mkdir(parents=True, exist_ok=True)
        self.load_files()

    def __repr__(self):
        return f'{self.__class__.__name__}({self.arb})'

    @property
    def disabled(self) -> bool:
        if self._flag_disabled or self.arb.flag_disabled:
            return True
        if any(pool.status == PoolStatus.disabled for pool in self.pools):
            self.disable()
            return True
        return False

    def disable(self):
        self._flag_disabled = True
        self.arb.flag_disabled = True
        self._change_summary_file = True

    def is_running(self, block_number: int = None) -> bool:
        is_running = self.arb.is_running(block_number)
        if not is_running and self.arb.flag_execute:
            tx = self.arb.get_tx_stats()
            if tx not in self.transactions:
                self._load_transaction(tx)
                self._new_transactions = True
                self._change_summary_file = True
        return is_running

    def load_files(self):
        self._load_summary_file()
        self._load_transaction_files()

    def _load_summary_file(self):
        if self.summary_filepath.exists():
            summary_data = json.load(open(self.summary_filepath))
        elif self.summary_backup_filepath.exists():
            summary_data = json.load(open(self.summary_backup_filepath))
        else:
            summary_data = {}
        if 'addresses' in summary_data:
            assert self.arb.token_first.address == summary_data['addresses']['token_fist']
            assert self.arb.token_last.address == summary_data['addresses']['token_last']
            assert self.route_0_addresses == summary_data['addresses']['route_0']
            assert self.route_1_addresses == summary_data['addresses']['route_1']
        self._flag_disabled = summary_data.get('disabled', False)
        self.n_successes = summary_data.get('n_successes', 0)
        self.n_failures = summary_data.get('n_failures', 0)

    def _load_transaction_files(self):
        tx_files = sorted(self.transactions_directory.iterdir())[-MAX_TRANSACTIONS_STORE_PER_PAIR:]
        for tx_file in tx_files:
            tx = json.load(open(tx_file))
            tx['_written'] = True
            self._load_transaction(tx, skip_check=True)

    def _load_transaction(self, tx: dict, skip_check: bool = False):
        self.transactions.append(tx)
        self.transactions = self.transactions[-MAX_TRANSACTIONS_STORE_PER_PAIR:]
        for pool in self.pools:
            pool.add_tx(tx, skip_check)
        if tx['tx_status'] == TxStatus.succeeded:
            self.n_successes += 1
        elif tx['tx_status'] == TxStatus.failed:
            self.n_failures += 1

    def update_files(self):
        if self._change_summary_file:
            self._update_summary_file()
            self._change_summary_file = False
        if self._new_transactions:
            self._save_new_transactions()
            self._new_transactions = False

    def _update_summary_file(self):
        data = {
            'addresses': {
                'token_fist': self.arb.token_first.address,
                'token_last': self.arb.token_last.address,
                'route_0': self.route_0_addresses,
                'route_1': self.route_1_addresses,
            },
            'disabled': self.disabled,
            'n_successes': self.n_successes,
            'n_failures': self.n_failures,
        }
        if self.summary_filepath.exists():
            os.rename(self.summary_filepath, self.summary_backup_filepath)
        with open(self.summary_filepath, 'w') as f:
            json.dump(data, f, indent=4)

    def _save_new_transactions(self):
        for tx in reversed(self.transactions):
            if tx.get('_written'):
                return
            with open(self.transactions_directory / f'{tx["block_found"]}.json', 'w') as f:
                json.dump(tx, f, indent=4)
            tx['_written'] = True

    def test_pools(self) -> bool:
        if all(pool.status == PoolStatus.enabled for pool in self.pools):
            return True
        try:
            self.arb.dry_run()
        except Exception as e:
            str_error = json.dumps([arg for arg in e.args])
            if PAT_ERROR_REMOVE_POOL.search(str_error):
                log.info(f'Arbitrage failed test with {str_error}, disabling new pools.')
                for pool in self.pools:
                    if pool.status == PoolStatus.untested:
                        pool.disable()
            else:
                log.info(f'Arbitrage failed test with {str_error}, may retry later.')
            return False
        log.info('Arbitrage test succeeded, enabling pools.')
        for pool in self.pools:
            pool.enable()
        return True


class ManagedPool:
    def __init__(
        self,
        lp: LiquidityPool,
        min_success_rate: int,
        min_success_rate_sample_size: int,
        max_repeated_failures: int,
        blocks_per_transaction: int,
    ):
        self.lp = lp
        self.min_success_rate = min_success_rate
        self.min_success_rate_sample_size = min_success_rate_sample_size
        self.max_repeated_failures = max_repeated_failures
        self.blocks_per_transaction = blocks_per_transaction

        self._status = PoolStatus.untested
        self.n_successes = 0
        self.n_failures = 0
        self.block_failures: list[int] = []

    def __repr__(self):
        return f'{self.__class__.__name__}({self.lp})'

    @property
    def status(self) -> PoolStatus:
        if self._status == PoolStatus.untested and self.n_successes > 0:
            self.enable()
        return self._status

    def enable(self):
        self._status = PoolStatus.enabled

    def disable(self):
        self._status = PoolStatus.disabled

    def add_tx(self, tx: dict, skip_check: bool = False):
        if tx['tx_status'] == TxStatus.succeeded:
            self.n_successes += 1
            self.block_failures = []
        elif tx['tx_status'] == TxStatus.failed:
            self.n_failures += 1
            self.block_failures.append(tx['block_found'])
            if not skip_check:
                self.check_disable()

    def sort_and_check(self):
        block_failures = sorted(self.block_failures)
        for i in range(len(block_failures) - self.max_repeated_failures):
            n_blocks = block_failures[i] - block_failures[i + self.max_repeated_failures] + 1
            if n_blocks <= self.max_repeated_failures * self.blocks_per_transaction:
                log.info(
                    f'{self}: {self.max_repeated_failures} repeated failures at block '
                    f'{block_failures[i + self.max_repeated_failures]}, disabling pool'
                )
                self.disable()
                break
        self.block_failures = block_failures[-self.max_repeated_failures:]

    def check_disable(self):
        n_total = self.n_successes + self.n_failures
        if (
            n_total >= self.min_success_rate_sample_size
            and (success_rate := self.n_successes / n_total) < self.min_success_rate
        ):
            log.info(f'{self}: {success_rate=:.1%} lower than minimum, disabling pool')
            self.disable()
        elif len(self.block_failures) >= self.max_repeated_failures:
            self.block_failures = self.block_failures[-self.max_repeated_failures:]
            n_blocks = self.block_failures[-1] - self.block_failures[0] + 1
            if n_blocks <= self.max_repeated_failures * self.blocks_per_transaction:
                log.info(
                    f'{self}: {len(self.block_failures)} repeated '
                    f'failures last {n_blocks} blocks, disabling pool'
                )
                self.disable()


class PairManager:
    def __init__(
        self,
        addresses_directory: PathLike,
        arbitrage_pairs: list[ArbitragePairV1],
        web3: Web3,
        min_profitability: float = DEFAULT_MIN_PROFITABILITY,
        max_total_repeated_failures: int = DEFAULT_MAX_TOTAL_REPEATED_FAILURES,
        min_pool_success_rate: float = DEFAULT_MIN_POOL_SUCCESS_RATE,
        min_pool_success_rate_sample_size: int = DEFAULT_MIN_POOL_SUCCESS_RATE_SAMPLE_SIZE,
        max_pool_repeated_failures: int = DEFAULT_MAX_POOL_REPEATED_FAILURES,
    ):
        self.addresses_directory = pathlib.Path(addresses_directory)
        self.removed_pools: list[str] = _load_removed_pools(self.addresses_directory)
        self.web3 = web3
        self.min_profitability = min_profitability
        self.max_total_repeated_failures = max_total_repeated_failures
        self.block_failures = []

        all_pools = {pool for arb in arbitrage_pairs for pool in arb.pools}
        self.blocks_per_transaction = max(arb.min_confirmations for arb in arbitrage_pairs) + 2
        self.pools = [
            ManagedPool(
                lp,
                min_pool_success_rate,
                min_pool_success_rate_sample_size,
                max_pool_repeated_failures,
                self.blocks_per_transaction,
            )
            for lp in all_pools
        ]
        self._running_pools = set()
        self._arbitrage_pairs = [
            ManagedPair(arb, self.pools, self.addresses_directory)
            for arb in arbitrage_pairs
        ]
        for pool in self.pools:
            pool.sort_and_check()
        tools.process.register_exit_handle(self._handle_exit)

    def __repr__(self):
        return f'{self.__class__.__name__}(n_pairs={len(self.arbitrage_pairs)})'

    @property
    def arbitrage_pairs(self) -> list[ManagedPair]:
        return [
            arb_pair
            for arb_pair in self._arbitrage_pairs
            if not arb_pair.disabled
        ]

    def update_and_execute(self, block_number: int = None):
        if block_number is None:
            return  # Case when process is shutting down
        next_round_pairs = self._get_next_round_pairs(block_number)  # Needs to be called before checking for status  # noqa: E501
        if any(arb_pair.arb.tx_status == TxStatus.succeeded for arb_pair in self.arbitrage_pairs):
            self.block_failures = []
        if any(arb_pair.arb.tx_status == TxStatus.failed for arb_pair in self.arbitrage_pairs):
            self.block_failures.append(block_number)
            self._check_shutdown()
        self._update_and_execute(block_number, next_round_pairs)
        self._update_arb_pairs()
        self._update_pools()
        log.info(f'{self}: Completed run on {block_number=}')

    def _get_next_round_pairs(self, block_number: int) -> list[ManagedPair]:
        self._running_pools.clear()
        for pair in self.arbitrage_pairs:
            if pair.is_running(block_number):
                self._running_pools.update(pair.pools)
        return [
            pair
            for pair in self.arbitrage_pairs
            if not pair.pools & self._running_pools
        ]

    def _update_and_execute(self, block_number: int, next_round_pairs: list[ManagedPair]) -> bool:
        best_pairs = []
        for pair in next_round_pairs:
            pair.arb.update_estimate(block_number)
            if pair.arb.estimated_net_result_usd > self.min_profitability:
                best_pairs.append(pair)
        if not best_pairs:
            return
        best_pairs = sorted(best_pairs, key=lambda x: x.arb.adjusted_profit, reverse=True)
        log.info(f'Arbitrage opportunity(ies) found on block {block_number}')
        for pair in best_pairs:
            if not pair.test_pools() or pair.pools & self._running_pools:
                continue
            if (current_block := self.web3.eth.block_number) != block_number:
                log.warning(
                    'Latest block advanced since beggining of iteration: '
                    f'{block_number=} vs {current_block=}'
                )
                return
            self._running_pools.update(pair.pools)
            pair.arb.execute()

    def _update_arb_pairs(self):
        for arb_pair in self._arbitrage_pairs:
            arb_pair.update_files()
        self._arbitrage_pairs = self.arbitrage_pairs

    def _update_pools(self):
        remove_pools = [
            pool.lp.address
            for pool in self.pools
            if pool.status == PoolStatus.disabled and pool.lp.address not in self.removed_pools
        ]
        if remove_pools:
            self.removed_pools.extend(remove_pools)
            removed_pools_file = self.addresses_directory / REMOVED_POOLS_FILE
            removed_pools_backup_file = self.addresses_directory / REMOVED_POOLS_BACKUP_FILE
            if removed_pools_file.exists():
                os.rename(removed_pools_file, removed_pools_backup_file)
            with open(removed_pools_file, 'w') as f:
                json.dump(self.removed_pools, f, indent=4)

    def _check_shutdown(self):
        if len(self.block_failures) >= self.max_total_repeated_failures:
            self.block_failures = self.block_failures[-self.max_total_repeated_failures:]
            n_blocks = self.block_failures[-1] - self.block_failures[0] + 1
            if n_blocks <= self.max_total_repeated_failures * self.blocks_per_transaction:
                log.info(f'At least {len(self.block_failures)} failures last {n_blocks} blocks')
                sys.exit()

    def _handle_exit(self, *args):
        log.info(f'{self}: preparing for shut down')
        for _ in range(10):
            if any(pair.is_running() for pair in self.arbitrage_pairs):
                log.info('Waiting for transactions receipts')
                time.sleep(0.6)  # 'docker stop' waits for 10 seconds before program closes
            else:
                break
        log.info('Updating pairs')
        self._update_arb_pairs()
        log.info('Updating pools')
        self._update_pools()
        log.info('Finished updates')

    @staticmethod
    def load_dex_protocols(
        addresses_directory: PathLike,
        dex_protocols: dict[str, Type[DexProtocol]],
        web3: Web3,
        load_removed: bool = False,
    ) -> dict[str, DexProtocol]:
        addresses_directory = pathlib.Path(addresses_directory)
        pools_file = addresses_directory / POOLS_FILE
        if not pools_file.exists():
            raise Exception(f'No active pools file found at {pools_file}')
        dict_addresses = json.load(open(pools_file))
        removed_pools = _load_removed_pools(addresses_directory) if not load_removed else []
        dexes = {}
        for dex_name, dex_cls in dex_protocols.items():
            addresses = [addr for addr in dict_addresses[dex_name] if addr not in removed_pools]
            dexes[dex_name] = dex_cls(pools_addresses=addresses, web3=web3)
        return dexes

    @staticmethod
    def get_v1_pool_arguments(
        dexes: Iterable[DexProtocol],
        web3: Web3,
        max_hops_dex_1: int = DEFAULT_MAX_HOPS_DEX_1,
        self_trade: bool = False,
        load_low_liquidity: bool = False,
    ) -> Iterable[tuple[DexProtocol, DexProtocol]]:
        all_tokens = {token for dex in dexes for token in dex.tokens}
        all_pools = [pool for dex in dexes for pool in dex.pools]
        prices = {}
        for token in all_tokens:
            if not load_low_liquidity:
                try:
                    prices[token] = tools.price.get_price_usd(token, all_pools, web3)
                except InsufficientLiquidity:
                    pass
        for dex_0, dex_1 in _get_dex_pairs(dexes, self_trade):
            for pool_0 in dex_0.pools:
                for token_first, token_last in permutations(pool_0.tokens):
                    if token_last not in prices and not load_low_liquidity:
                        continue
                    if load_low_liquidity:
                        min_amount_last = TokenAmount(token_last, 0)
                    else:
                        price_unit = prices[token_last] / 10 ** token_last.decimals
                        min_amount_last = TokenAmount(
                            token_last,
                            round(MIN_AMOUNT_OUT_USD / price_unit)
                        )

                    # The order for token_first/token_last is inverted for the second route_0
                    route_0 = Route([pool_0], [token_last, token_first])

                    pools_1 = [pool for pool in dex_1.pools if pool != pool_0]
                    dex_1_routes = _get_routes(
                        pools_1, token_first, min_amount_last, max_hops_dex_1)

                    for route_1 in dex_1_routes:
                        yield {
                            'token_first': token_first,
                            'token_last': token_last,
                            'route_0': route_0,
                            'route_1': route_1,
                            'dex_0': dex_0,
                            'dex_1': dex_1,
                            'web3': web3,
                        }


def _load_removed_pools(addresses_directory: pathlib.Path) -> list[str]:
    removed_pools_file = addresses_directory / REMOVED_POOLS_FILE
    if removed_pools_file.exists():
        return json.load(open(removed_pools_file))

    removed_pools_backup_file = addresses_directory / REMOVED_POOLS_BACKUP_FILE
    if removed_pools_backup_file.exists():
        return json.load(open(removed_pools_backup_file))
    return []


def _get_dex_pairs(
    dexes: list[DexProtocol],
    self_trade: bool,
) -> Iterable[tuple[DexProtocol, DexProtocol]]:
    if self_trade:
        for dex_0, dex_1 in product(dexes, repeat=2):
            yield dex_0, dex_1
    else:
        for dex_0, dex_1 in permutations(dexes, 2):
            yield dex_0, dex_1


def _get_routes(
    pools: list[LiquidityPool],
    token_in: Token,
    min_amount_out: TokenAmount,
    max_hops: int,
    current_pools: list[LiquidityPool] = None,
    original_min_amount_out: TokenAmount = None,
    routes: list[RoutePairs] = None,
) -> list[RoutePairs]:
    current_pools = [] if current_pools is None else current_pools
    if original_min_amount_out is None:
        original_min_amount_out = min_amount_out
    routes = [] if routes is None else routes
    for pool in pools:
        if min_amount_out.token not in pool.tokens:
            continue
        try:
            amount_in = pool.get_amount_in(min_amount_out)
            assert amount_in >= 0
        except (InsufficientLiquidity, AssertionError):
            continue
        if amount_in.token == token_in:
            # End of recursion
            routes.append(RoutePairs([pool, *current_pools], token_in, min_amount_out.token))
        elif max_hops > 1 and len(pools) > 1:
            next_recursion_pools = copy(pools)
            next_recursion_pools.remove(pool)
            _get_routes(
                pools=next_recursion_pools,
                token_in=token_in,
                min_amount_out=amount_in,
                max_hops=max_hops - 1,
                current_pools=[pool, *current_pools],
                original_min_amount_out=original_min_amount_out,
                routes=routes,
            )
    return routes
