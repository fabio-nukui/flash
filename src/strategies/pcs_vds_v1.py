# Pancakeswap (PCS) x ValueDefiSwap (VDS)

import logging
from typing import Iterable, Union

from web3 import Web3
from web3.contract import Contract

import tools
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDex, ValueDefiSwapDex

log = logging.getLogger(__name__)

# Strategy parameters
MIN_ESTIMATED_PROFIT = 1
DISABLE_SAMPLE_SIZE = 50
GAS_SHARE_OF_PROFIT = 0.26
DEX_PROTOCOLS = {
    'pcs_dex': PancakeswapDex,
    'vds_dex': ValueDefiSwapDex,
}

# Gas-related parameters; data from notebooks/pcs_vds_analysis.ipynb (2021-04-20)
GAS_COST_PCS_1_CHI_ON = 156_279.7
GAS_COST_VDS_1_CHI_ON = 139_586.4
GAS_INCREASE_WITH_HOP = 0.266831606034439

# Created with notebooks/2021-04-12-pcs_vds_v1.ipynb
ADDRESS_DIRECTORY = 'strategy_files/pcs_vds_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsVdsV1B.json'


class PcsVdsPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.trade_1.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if type(self.dex_1) == PancakeswapDex:
            return round(GAS_COST_PCS_1_CHI_ON * gas_cost_multiplier)
        else:
            return round(GAS_COST_VDS_1_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if type(self.dex_1) == PancakeswapDex:
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapVdsFirst

    def _get_function_arguments(self) -> dict():
        if type(self.dex_1) == PancakeswapDex:
            path = [
                self.trade_0.route.pools[0].address,
                *(t.address for t in self.trade_1.route.tokens)
            ]
        else:
            path = [
                self.token_first.address,
                self.token_last.address,
                *(p.address for p in self.trade_1.route.pools)
            ]
        return {
            'path': path,
            'amountLast': self.amount_last.amount,
        }


def get_share_of_profit(params: dict):
    reduced_gas_share_pools = [
        '0xfC207DB720851f52545229E406068b205E02B952',  # pcs xBLZD/WBNB
        '0xb7f68eA4Ec4ea7Ee04E7Ed33B5dA85d7B43057D6',  # vds xBLZD/WBNB
        '0xBFa35CD43fad8eabbA8D75b1f4bb120DCF409755',  # pcs BLUE/GREEN
        '0x1ecA68Ca40c0849AFA8C3A88Be0e06e99f701eF1',  # vds BLUE/GREEN
    ]
    route_addresses = [
        pool.address
        for pool in params['route_0'].pools + params['route_1'].pools
    ]
    if any(addr in route_addresses for addr in reduced_gas_share_pools):
        return 0.02
    return GAS_SHARE_OF_PROFIT


def load_arbitrage_pairs(
    dexes: Iterable[Union[PancakeswapDex, ValueDefiSwapDex]],
    contract: Contract,
    web3: Web3,
    load_low_liquidity: bool = False,
) -> list[PcsVdsPair]:
    return [
        PcsVdsPair(**params, contract=contract, gas_share_of_profit=get_share_of_profit(params))
        for params in PairManager.get_v1_pool_arguments(
            dexes,
            web3,
            load_low_liquidity=load_low_liquidity,
        )
    ]


def run():
    web3 = tools.w3.get_web3(verbose=True)
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, DEX_PROTOCOLS, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = load_arbitrage_pairs(dexes.values(), contract, web3)
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks(update_block_config=True):
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
