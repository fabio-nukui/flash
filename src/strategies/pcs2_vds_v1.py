# PancakeswapV2 (PCS2) x ValueDefiSwap (VDS)

import logging

import tools
import configs
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDexV2, ValueDefiSwapDex

log = logging.getLogger(__name__)

# Gas-related parameters; extrapoated from from notebooks/pcs_vds_analysis.ipynb (2021-04-20)
GAS_COST_PCS_FIRST_CHI_ON = 156_279.7
GAS_COST_VDS_FIRST_CHI_ON = 139_586.4
GAS_INCREASE_WITH_HOP = 0.266831606034439
GAS_SHARE_OF_PROFIT = 0.24

# Created with notebooks/strategies/pcs2_vds_v1.ipynb (2021-04-25)
ADDRESS_DIRECTORY = 'strategy_files/pcs2_vds_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/Pcs2VdsV1.json'


class Pcs2VdsPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if type(self.first_dex) == PancakeswapDexV2:
            return int(GAS_COST_PCS_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_VDS_FIRST_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if type(self.first_dex) == PancakeswapDexV2:
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapVdsFirst

    def _get_function_arguments(self) -> dict():
        if type(self.first_dex) == PancakeswapDexV2:
            path = [
                self.second_trade.route.pools[0].address,
                *(t.address for t in self.first_trade.route.tokens)
            ]
        else:
            path = [
                self.token_first.address,
                self.token_last.address,
                *(p.address for p in self.first_trade.route.pools)
            ]
        return {'path': path}


def get_share_of_profit(params: dict):
    reduced_gas_share_pools = [
        '0xD9002B7E7d63A71F04a16840DA028e1cd534889D',  # pcs2 xBLZD/WBNB
        '0xb7f68eA4Ec4ea7Ee04E7Ed33B5dA85d7B43057D6',  # vds xBLZD/WBNB
    ]
    route_addresses = [
        pool.address
        for pool in params['first_route'].pools + params['second_route'].pools
    ]
    if any(addr in route_addresses for addr in reduced_gas_share_pools):
        return 0.01
    return GAS_SHARE_OF_PROFIT


def run():
    web3 = tools.w3.get_web3(verbose=True)
    dex_protocols = {
        'pcs2_dex': PancakeswapDexV2,
        'vds_dex': ValueDefiSwapDex,
    }
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, dex_protocols, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        Pcs2VdsPair(**params, contract=contract, gas_share_of_profit=get_share_of_profit(params))
        for params in PairManager.get_v1_pool_arguments(dexes.values(), web3)
    ]
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
