# Pancakeswap (PCS) x PancakeswapV2 (PCS2)

import logging
from typing import Iterable, Union

from web3 import Web3
from web3.contract import Contract

import arbitrage
import tools
from arbitrage import ArbitragePairV1, PairManager
from dex import MDex, PancakeswapDex, PancakeswapDexV2, ValueDefiSwapDex

log = logging.getLogger(__name__)

# Strategy parameters
MAX_HOPS_DEX_1 = 2
SELF_TRADE = True
DEX_PROTOCOLS = {
    'pcs_dex': PancakeswapDex,
    'pcs2_dex': PancakeswapDexV2,
}
WRAPPED_CURRENCY_SWAP = True
DEX_PROTOCOL_CODES = {
    PancakeswapDex: 0,
    PancakeswapDexV2: 1,
    MDex: 2,
}

# Data from notebooks/profitability_analysis.ipynb (2021-05-03)
GAS_COST_W_SWAP = 107_000
GAS_COST_FLASH_SWAP = 137_392.4
GAS_INCREASE_WITH_HOP = 0.349470567513196
GAS_SHARE_OF_PROFIT = 0.26
MAX_GAS_MULTIPLIER = 7

# Created with notebooks/strageties/pcs_pcs2_v1.ipynb (2021-05-01)
ADDRESS_DIRECTORY = 'strategy_files/pcs_pcs2_v1'
CONTRACT_DATA_FILEPATH = 'build/contracts/MultiV1.json'


class MultiPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.trade_1.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if not self.execute_w_swap:
            return round(GAS_COST_FLASH_SWAP * gas_cost_multiplier)
        return round(GAS_COST_W_SWAP * gas_cost_multiplier)

    def _get_contract_function(self):
        if not self.execute_w_swap:
            return self.contract.functions.flash_09lc
        return self.contract.functions.swap_3gMy

    def _get_function_arguments(self) -> dict:
        dex_0 = DEX_PROTOCOL_CODES[type(self.dex_0)]
        dex_1 = DEX_PROTOCOL_CODES[type(self.dex_1)]
        tokens = self.route_1.tokens[:-1] if self.execute_w_swap else self.route_1.tokens
        data0, data1 = arbitrage.encode_data.encode_data_v2(
            dex_0,
            dex_1,
            self._amount_last_exp,
            self._amount_last_mant,
            tokens,
        )
        return {
            'data0': data0,
            'data1': data1,
        }


def get_share_of_profit(params: dict):
    reduced_gas_share_pools = {
        '0xfC207DB720851f52545229E406068b205E02B952': 0.01,  # pcs xBLZD/WBNB
        '0xD9002B7E7d63A71F04a16840DA028e1cd534889D': 0.01,  # pcs2 xBLZD/WBNB
        '0x3Ee4de968E47877F432226d6a9A0DAD6EAc6001b': 0.14,  # pcs sALPACA/ALPACA
        '0x6615187234104CE7d2fb1deF75eDb9d77408230D': 0.14,  # pcs2 sALPACA/ALPACA
    }
    for pool in params['route_0'].pools + params['route_1'].pools:
        if pool.address in reduced_gas_share_pools:
            return reduced_gas_share_pools[pool.address]
    return GAS_SHARE_OF_PROFIT


def load_arbitrage_pairs(
    dexes: Iterable[Union[PancakeswapDex, PancakeswapDexV2]],
    contract: Contract,
    web3: Web3,
    load_low_liquidity: bool = False,
) -> list[MultiPair]:
    return [
        MultiPair(
            **params,
            contract=contract,
            gas_share_of_profit=get_share_of_profit(params),
            max_gas_multiplier=MAX_GAS_MULTIPLIER,
            decomposer_function=arbitrage.decompose_amount_v2,
        )
        for params in PairManager.get_v1_pool_arguments(
            dexes,
            web3,
            MAX_HOPS_DEX_1,
            SELF_TRADE,
            load_low_liquidity,
        )
    ]


def run():
    web3 = tools.w3.get_web3(verbose=True)
    dict_dex = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, DEX_PROTOCOLS, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = load_arbitrage_pairs(dict_dex.values(), contract, web3)
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks(update_block_config=True):
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
