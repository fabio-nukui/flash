# Pancakeswap (PCS) x ValueDefiSwap (VDS)

import logging

import tools
import configs
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDex, ValueDefiSwapDex

log = logging.getLogger(__name__)

# Strategy parameters
MIN_ESTIMATED_PROFIT = 1
DISABLE_SAMPLE_SIZE = 50

# Gas-related parameters; data from notebooks/pcs_vds_analysis.ipynb (2021-04-20)
GAS_COST_PCS_FIRST_CHI_ON = 156_279.7
GAS_COST_VDS_FIRST_CHI_ON = 139_586.4
GAS_INCREASE_WITH_HOP = 0.266831606034439

# Created with notebooks/2021-04-12-pcs_vds_v1.ipynb
ADDRESS_DIRECTORY = 'strategy_files/pcs_vds_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsVdsV1B.json'


class PcsVdsPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if isinstance(self.first_dex, PancakeswapDex):
            return int(GAS_COST_PCS_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_VDS_FIRST_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapVdsFirst

    def _get_path_argument(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return [
                self.second_trade.route.pools[0].address,
                *(t.address for t in self.first_trade.route.tokens)
            ]
        return [
            self.token_first.address,
            self.token_last.address,
            *(p.address for p in self.first_trade.route.pools)
        ]


def run():
    web3 = tools.w3.get_web3(verbose=True)
    dex_protocols = {
        'pcs_dex': PancakeswapDex,
        'vds_dex': ValueDefiSwapDex,
    }
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, dex_protocols, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        PcsVdsPair(**params, contract=contract)
        for params in PairManager.get_v1_pool_arguments(dexes.values(), web3)
    ]
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
