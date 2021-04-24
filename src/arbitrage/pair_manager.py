import json
import logging
import pathlib
import re
from collections import defaultdict
from typing import Type, Union

from web3 import Web3

from dex import DexProtocol

from .arbitrage_pair_v1 import ArbitragePairV1

log = logging.getLogger(__name__)

POOLS_FILE = 'pools.json'
REMOVED_POOLS_FILE = 'pools_removed.json'
TESTED_POOLS_FILE = 'pools_tested.json'
TRANSACTION_COUNTS_FILE = 'transaction_counts.json'

DEFAULT_DISABLE_SAMPLE_SIZE = 20
DEFAULT_MIN_SUCCESS_RATE = 0.2

# Disable if testing transaction raises message with 'K' https://uniswap.org/docs/v2/smart-contracts/common-errors/  # noqa: E501
PAT_ERROR_REMOVE_POOL = re.compile('K')


class PairManager:
    def __init__(
        self,
        addresses_directory: Union[str, pathlib.Path],
        arbitrage_pairs: list[ArbitragePairV1],
        web3: Web3,
        min_profitability: float = 0.0,
        disable_sample_size: int = DEFAULT_DISABLE_SAMPLE_SIZE,
        min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE,
    ):
        addresses_directory = pathlib.Path(addresses_directory)
        self.pools_file = addresses_directory / POOLS_FILE
        if not self.pools_file.exists():
            raise Exception(f'No active pools file found {self.pools_file}')
        self.removed_pools_file = addresses_directory / REMOVED_POOLS_FILE
        self.tested_pools_file = addresses_directory / TESTED_POOLS_FILE
        self.transaction_counts_file = addresses_directory / TRANSACTION_COUNTS_FILE
        self.arbitrage_pairs = arbitrage_pairs
        self.web3 = web3
        self.min_profitability = min_profitability
        self.disable_sample_size = disable_sample_size
        self.min_success_rate = min_success_rate

        self.removed_pools: list[dict[str, str]] = []
        self.tested_pools: list[str] = []
        self.transaction_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        if self.removed_pools_file.exists():
            self.removed_pools = json.load(open(self.removed_pools_file))
        if self.tested_pools_file.exists():
            self.tested_pools = json.load(open(self.tested_pools_file))
        if self.transaction_counts_file.exists():
            self.transaction_counts.update(json.load(open(self.transaction_counts_file)))

        self._new_removed_pool = False
        self._new_tested_pool = False
        self._new_transaction_count = False

    def __repr__(self):
        return f'{self.__class__.__name__}(n_pairs={len(self.arbitrage_pairs)})'

    def get_next_round_pairs(
        self,
        block_number: int,
        running_arbitrages: list[ArbitragePairV1],
    ) -> list[ArbitragePairV1]:
        running_tokens = set()
        for pair in running_arbitrages:
            for token in pair.first_trade.route.tokens:
                running_tokens.add(token)
            for token in pair.second_trade.route.tokens:
                running_tokens.add(token)
        return [
            pair
            for pair in self.arbitrage_pairs
            if pair.token_first not in running_tokens and pair.token_last not in running_tokens
        ]

    def _check_remove_pool(self, pool_address: str):
        counts = self.transaction_counts[pool_address]
        if (n_total := counts['failed'] + counts['succeded']) < self.disable_sample_size:
            return
        if counts['failed'] / n_total < self.min_success_rate:
            self._new_removed_pool = True
            if pool_address not in self.removed_pools:
                log.info(f'New removed pool: {pool_address}')
                self.removed_pools.append(pool_address)

    def _check_new_transactions(self):
        for arb in self.arbitrage_pairs:
            if arb.tx_succeeded is not None:
                self._update_transactions_file = True
                for pool in arb.pools:
                    if arb.tx_succeeded:
                        self.transaction_counts[pool.address]['succeded'] += 1
                    else:
                        self.transaction_counts[pool.address]['failed'] += 1
                        self._check_remove_pool(pool.address)
                arb.tx_succeeded = None

    def _update_and_execute(self, block_number: int):
        running_arbitrages = [
            pair
            for pair in self.arbitrage_pairs
            if pair.is_running(block_number)
        ]
        self._check_new_transactions()  # Needs to be called between pair.is_running() and pair.execute()  # noqa: E501
        pairs = []
        for arb_pair in self.get_next_round_pairs(block_number, running_arbitrages):
            arb_pair.update_estimate(block_number)
            if arb_pair.estimated_net_result_usd > self.min_profitability:
                pairs.append(arb_pair)
        if not pairs:
            return
        best_arbitrage = max(pairs, key=lambda x: x.estimated_net_result_usd)
        log.info(f'Arbitrage opportunity found on block {block_number}')
        if (current_block := self.web3.eth.block_number) != block_number:
            log.warning(
                'Latest block advanced since beggining of iteration: '
                f'{block_number=} vs {current_block=}'
            )
            return
        valid_execution = True
        if any(pool.address not in self.tested_pools for pool in best_arbitrage.execution_pools):
            valid_execution = self._test_arbitrage(best_arbitrage)
        if valid_execution:
            best_arbitrage.execute()

    def update_and_execute(self, block_number: int):
        self._update_and_execute(block_number)
        self._update_arb_pairs()
        self._update_files()

    def _test_arbitrage(self, arb: ArbitragePairV1) -> bool:
        str_error = ''
        try:
            arb.dry_run()
        except Exception as e:
            str_error = json.dumps([arg for arg in e.args])
        match_remove_pool = PAT_ERROR_REMOVE_POOL.search(str_error)

        self._new_tested_pool = True
        for pool in arb.execution_pools:
            if pool.address not in self.tested_pools:
                log.debug(f'New tested pool: {pool}')
                self.tested_pools.append(pool.address)

        if match_remove_pool:
            log.info('Arbitrage failed test, removing its pools from strategies')
            self._new_removed_pool = True
            for pool in arb.execution_pools:
                if pool.address not in self.removed_pools:
                    log.info(f'New removed pool: {pool}')
                    self.removed_pools.append(pool.address)
        return not match_remove_pool

    def _update_arb_pairs(self):
        self.arbitrage_pairs = [pair for pair in self.arbitrage_pairs if not pair.is_disabled]
        if self._new_removed_pool:
            for pair in self.arbitrage_pairs:
                for dex in (pair.first_dex, pair.second_dex):
                    dex.pools = [
                        pool
                        for pool in dex.pools
                        if pool.address not in self.removed_pools
                    ]

    def _update_files(self):
        if self._new_removed_pool:
            with open(self.removed_pools_file, 'w') as f:
                json.dump(self.removed_pools, f, indent=4)
            self._new_removed_pool = False

        if self._new_tested_pool:
            with open(self.tested_pools_file, 'w') as f:
                json.dump(self.tested_pools, f, indent=4)
            self._new_tested_pool = False

        if self._new_transaction_count:
            with open(self.transaction_counts_file, 'w') as f:
                json.dump(self.transaction_counts, f, indent=4)
            self._new_transaction_count = False

    @staticmethod
    def load_dex_protocols(
        address_directory: Union[str, pathlib.Path],
        dex_protocols: dict[str, Type[DexProtocol]],
        web3: Web3,
    ) -> dict[str, DexProtocol]:
        pools_file = pathlib.Path(address_directory) / POOLS_FILE
        removed_pools_file = pathlib.Path(address_directory) / REMOVED_POOLS_FILE
        if not pools_file.exists():
            raise Exception(f'No active pools file found at {pools_file}')
        dict_addresses = json.load(open(pools_file))
        removed_pools = json.load(open(removed_pools_file)) if removed_pools_file.exists() else []
        dexes = {}
        for dex_name, dex_cls in dex_protocols.items():
            addresses = [addr for addr in dict_addresses[dex_name] if addr not in removed_pools]
            dexes[dex_name] = dex_cls(pools_addresses=addresses)
        return dexes
