# Pancakeswap (PCS) x MDex (MDX)

import logging

import tools
import configs
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDex, MDex

log = logging.getLogger(__name__)

# Strategy params
GAS_SHARE_OF_PROFIT = 0.27

# Based on notebooks/analysis/pcs_mdx_analysis_v1.ipynb (2021-04-23)
GAS_COST_PCS_FIRST_CHI_ON = 140_575.7
GAS_COST_MDX_FIRST_CHI_ON = 138_368.1
GAS_INCREASE_WITH_HOP = 0.2908916690437962

# Created with notebooks/pcs_mdx_v1.ipynb (2021-04-22)
ADDRESS_DIRECTORY = 'strategy_files/pcs_mdx_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsMdxV1.json'


class PcsMdxPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if isinstance(self.first_dex, PancakeswapDex):
            return int(GAS_COST_PCS_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_MDX_FIRST_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapMdxFirst

    def _get_path_argument(self):
        return [t.address for t in self.first_trade.route.tokens]


def run():
    web3 = tools.w3.get_web3(verbose=True)
    dex_protocols = {
        'pcs_dex': PancakeswapDex,
        'mdx_dex': MDex,
    }
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, dex_protocols, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        PcsMdxPair(**params, contract=contract, gas_share_of_profit=GAS_SHARE_OF_PROFIT)
        for params in PairManager.get_v1_pool_arguments(dexes.values(), web3)
    ]
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
