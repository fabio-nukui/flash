# Pancakeswap (PCS) x ValueDefiSwap (VDS)

import logging
from itertools import permutations
from typing import Iterable

from web3 import Web3

import configs
import tools
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDex, PancakeswapDexV2

# Strategy parameters
MIN_ESTIMATED_PROFIT = 1
MAX_HOPS_FIRST_DEX = 1

# Estimations
GAS_COST_PCS1_FIRST_CHI_ON = 140_000
GAS_COST_PCS2_FIRST_CHI_ON = 140_000
GAS_INCREASE_WITH_HOP = 0.2908916690437962
GAS_SHARE_OF_PROFIT = 0.01
MAX_GAS_PRICE = 11 * 10 ** 9
RAISE_AT_EXCESSIVE_GAS_PRICE = False

# Created with notebooks/pcs_mdx_v1.ipynb (2021-04-22)
ADDRESS_DIRECTORY = 'strategy_files/pcs_pcs2_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsPcs2V1.json'

# Optimization params
USE_FALLBACK = False

log = logging.getLogger(__name__)


class PcsPcs2(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if isinstance(self.first_dex, PancakeswapDex):
            return int(GAS_COST_PCS1_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_PCS2_FIRST_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return self.contract.functions.swapPcs1First
        return self.contract.functions.swapPcs2First

    def _get_path_argument(self):
        return [t.address for t in self.first_trade.route.tokens]


def get_arbitrage_params(
    pcs_dex: PancakeswapDex,
    pcs2_dex: PancakeswapDexV2,
    web3: Web3,
) -> Iterable[dict]:
    for dex_0, dex_1 in permutations([pcs_dex, pcs2_dex]):
        for pool in dex_1.pools:
            for token_first, token_last in permutations(pool.tokens):
                first_dex_pools = [
                    p
                    for p in dex_0.pools
                    if token_first in p.tokens and token_last in p.tokens
                ]
                second_dex_pools = [
                    p
                    for p in dex_1.pools
                    if token_first in p.tokens and token_last in p.tokens
                ]
                if not first_dex_pools or not second_dex_pools:
                    continue
                yield {
                    'token_first': token_first,
                    'token_last': token_last,
                    'first_dex': dex_0.__class__(pools=first_dex_pools, web3=web3),
                    'second_dex': dex_1.__class__(pools=second_dex_pools, web3=web3),
                }


def run():
    web3 = tools.w3.get_web3(verbose=True)
    optimization_params = {'use_fallback': USE_FALLBACK}
    dex_protocols = {
        'pcs_dex': PancakeswapDex,
        'pcs2_dex': PancakeswapDexV2,
    }
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, dex_protocols, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        PcsPcs2(
            contract=contract,
            web3=web3,
            max_hops_first_dex=MAX_HOPS_FIRST_DEX,
            gas_share_of_profit=GAS_SHARE_OF_PROFIT,
            max_gas_price=MAX_GAS_PRICE,
            raise_at_excessive_gas_price=RAISE_AT_EXCESSIVE_GAS_PRICE,
            optimization_params=optimization_params,
            **params,
        )
        for params in get_arbitrage_params(dexes['pcs_dex'], dexes['pcs2_dex'], web3)
    ]
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3, MIN_ESTIMATED_PROFIT)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
