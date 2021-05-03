# Pancakeswap (PCS) x PancakeswapV2 (PCS2)

import logging
from typing import Iterable, Union

from web3 import Web3
from web3.contract import Contract

import configs
import tools
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDex, PancakeswapDexV2

log = logging.getLogger(__name__)

# Strategy parameters
MAX_HOPS_FIRST_DEX = 2
SELF_TRADE = True
DEX_PROTOCOLS = {
    'pcs_dex': PancakeswapDex,
    'pcs2_dex': PancakeswapDexV2,
}

# Estimations
GAS_COST_PCS1_FIRST_CHI_ON = 130_000
GAS_COST_PCS2_FIRST_CHI_ON = 130_000
GAS_INCREASE_WITH_HOP = 0.2908916690437962
GAS_SHARE_OF_PROFIT = 0.24
MAX_GAS_MULTIPLIER = 7

# Created with notebooks/pcs_mdx_v1.ipynb (2021-04-22)
ADDRESS_DIRECTORY = 'strategy_files/pcs_pcs2_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsPcs2V2B.json'

# Optimization params
USE_FALLBACK = False


class PcsPcs2Pair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if type(self.first_dex) == PancakeswapDex:
            return int(GAS_COST_PCS1_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_PCS2_FIRST_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        return self.contract.functions.swap_b2I

    def _get_function_arguments(self) -> dict:
        first_dex = '00' if type(self.first_dex) == PancakeswapDex else '01'
        second_dex = '00' if type(self.first_dex) == PancakeswapDexV2 else '01'
        path = ''.join(t.address[2:] for t in self.first_trade.route.tokens)
        return {
            'data': f'0x{first_dex}{second_dex}{path}',
        }


def get_share_of_profit(params: dict):
    reduced_gas_share_pools = {
        '0xfC207DB720851f52545229E406068b205E02B952': 0.01,  # pcs xBLZD/WBNB
        '0xD9002B7E7d63A71F04a16840DA028e1cd534889D': 0.01,  # pcs2 xBLZD/WBNB
        '0x3Ee4de968E47877F432226d6a9A0DAD6EAc6001b': 0.21,  # pcs sALPACA/ALPACA
        '0x6615187234104CE7d2fb1deF75eDb9d77408230D': 0.21,  # pcs2 sALPACA/ALPACA
    }
    for pool in params['first_route'].pools + params['second_route'].pools:
        if pool.address in reduced_gas_share_pools:
            return reduced_gas_share_pools[pool.address]
    return GAS_SHARE_OF_PROFIT


def load_arbitrage_pairs(
    dexes: Iterable[Union[PancakeswapDex, PancakeswapDexV2]],
    contract: Contract,
    web3: Web3,
    load_low_liquidity: bool = False,
) -> list[PcsPcs2Pair]:
    optimization_params = {'use_fallback': USE_FALLBACK}
    return [
        PcsPcs2Pair(
            **params,
            contract=contract,
            gas_share_of_profit=get_share_of_profit(params),
            max_gas_multiplier=MAX_GAS_MULTIPLIER,
            optimization_params=optimization_params,
        )
        for params in PairManager.get_v1_pool_arguments(
            dexes,
            web3,
            MAX_HOPS_FIRST_DEX,
            SELF_TRADE,
            load_low_liquidity,
        )
    ]


def run():
    web3 = tools.w3.get_web3(verbose=True)
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, DEX_PROTOCOLS, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = load_arbitrage_pairs(dexes.values(), contract, web3)
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
