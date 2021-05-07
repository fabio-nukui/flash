# Pancakeswap (PCS) x MDex (MDX)

import logging
from typing import Iterable, Union

from web3 import Web3
from web3.contract import Contract

import tools
from arbitrage import ArbitragePairV1, PairManager
from dex import MDex, PancakeswapDex

log = logging.getLogger(__name__)

# Strategy params
GAS_SHARE_OF_PROFIT = 0.27
DEX_PROTOCOLS = {
    'pcs_dex': PancakeswapDex,
    'mdx_dex': MDex,
}

# Based on notebooks/analysis/pcs_mdx_analysis_v1.ipynb (2021-04-23)
GAS_COST_PCS_1_CHI_ON = 140_575.7
GAS_COST_MDX_1_CHI_ON = 138_368.1
GAS_INCREASE_WITH_HOP = 0.2908916690437962

# Created with notebooks/pcs_mdx_v1.ipynb (2021-04-22)
ADDRESS_DIRECTORY = 'strategy_files/pcs_mdx_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsMdxV1.json'


class PcsMdxPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.trade_1.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if isinstance(self.dex_1, PancakeswapDex):
            return round(GAS_COST_PCS_1_CHI_ON * gas_cost_multiplier)
        else:
            return round(GAS_COST_MDX_1_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if isinstance(self.dex_1, PancakeswapDex):
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapMdxFirst

    def _get_function_arguments(self) -> dict:
        return {
            'path': [t.address for t in self.trade_1.route.tokens],
            'amountLast': self.amount_last.amount,
        }


def load_arbitrage_pairs(
    dexes: Iterable[Union[MDex, PancakeswapDex]],
    contract: Contract,
    web3: Web3,
    load_low_liquidity: bool = False,
) -> list[PcsMdxPair]:
    return [
        PcsMdxPair(**params, contract=contract, gas_share_of_profit=GAS_SHARE_OF_PROFIT)
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
