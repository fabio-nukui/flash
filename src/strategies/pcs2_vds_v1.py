# PancakeswapV2 (PCS2) x ValueDefiSwap (VDS)

import logging
from typing import Iterable, Union

from web3 import Web3
from web3.contract import Contract

import tools
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDexV2, ValueDefiSwapDex

log = logging.getLogger(__name__)

DEX_PROTOCOLS = {
    'pcs2_dex': PancakeswapDexV2,
    'vds_dex': ValueDefiSwapDex,
}

# Data from notebooks/profitability_analysis.ipynb (2021-05-03)
GAS_COST_PCS_1 = 157_139.86
GAS_COST_VDS_1 = 157_218.18
GAS_INCREASE_WITH_HOP = 0.25228347537028
GAS_SHARE_OF_PROFIT = 0.24

# Created with notebooks/strategies/pcs2_vds_v1.ipynb (2021-04-25)
ADDRESS_DIRECTORY = 'strategy_files/pcs2_vds_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/Pcs2VdsV1.json'


class Pcs2VdsPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.trade_1.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if type(self.dex_1) == PancakeswapDexV2:
            return round(GAS_COST_PCS_1 * gas_cost_multiplier)
        else:
            return round(GAS_COST_VDS_1 * gas_cost_multiplier)

    def _get_contract_function(self):
        if type(self.dex_1) == PancakeswapDexV2:
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapVdsFirst

    def _get_function_arguments(self) -> dict():
        if type(self.dex_1) == PancakeswapDexV2:
            path = [
                self.second_trade.route.pools[0].address,
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
        '0xD9002B7E7d63A71F04a16840DA028e1cd534889D',  # pcs2 xBLZD/WBNB
        '0xb7f68eA4Ec4ea7Ee04E7Ed33B5dA85d7B43057D6',  # vds xBLZD/WBNB
    ]
    route_addresses = [
        pool.address
        for pool in params['route_0'].pools + params['route_1'].pools
    ]
    if any(addr in route_addresses for addr in reduced_gas_share_pools):
        return 0.02
    return GAS_SHARE_OF_PROFIT


def load_arbitrage_pairs(
    dexes: Iterable[Union[PancakeswapDexV2, ValueDefiSwapDex]],
    contract: Contract,
    web3: Web3,
    load_low_liquidity: bool = False,
) -> list[Pcs2VdsPair]:
    return [
        Pcs2VdsPair(**params, contract=contract, gas_share_of_profit=get_share_of_profit(params))
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
