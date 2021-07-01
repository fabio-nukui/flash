# Pancakeswap (PCS) x PancakeswapV2 (PCS2)

import logging
from typing import Iterable, Union

from web3 import Web3
from web3.contract import Contract

import arbitrage
import tools
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDex, PancakeswapDexV2

log = logging.getLogger(__name__)

# Strategy parameters
MAX_HOPS_DEX_1 = 2
SELF_TRADE = True
DEX_PROTOCOLS = {
    'pcs_dex': PancakeswapDex,
    'pcs2_dex': PancakeswapDexV2,
}
W_SWAP_AVAILABLE = True

# Data from notebooks/profitability_analysis.ipynb (2021-05-03)
GAS_COST_W_SWAP = 107_000
GAS_COST_FLASH_SWAP = 137_392.4
GAS_INCREASE_WITH_HOP = 0.349470567513196
GAS_SHARE_OF_PROFIT = 0.24
MAX_GAS_MULTIPLIER = 7

# Created with notebooks/strageties/pcs_pcs2_v1.ipynb (2021-05-01)
ADDRESS_DIRECTORY = 'strategy_files/pcs_pcs2_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsPcs2V3.json'


class PcsPcs2Pair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.trade_1.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if not self.execute_w_swap:
            return round(GAS_COST_FLASH_SWAP * gas_cost_multiplier)
        return round(GAS_COST_W_SWAP * gas_cost_multiplier)

    def _get_contract_function(self):
        if not self.execute_w_swap:
            return self.contract.functions.flash_09lc
        if len(self.trade_1.route.pools) == 1:
            return self.contract.functions.swap32_bZf
        return self.contract.functions.swap64_Fi4

    def _get_function_arguments(self) -> dict:
        dex_0 = 0 if type(self.dex_0) == PancakeswapDex else 1
        dex_1 = 0 if type(self.dex_1) == PancakeswapDex else 1
        if not self.execute_w_swap:
            path = ''.join(t.address[2:] for t in self.trade_1.route.tokens)
            return {
                'data': f'0x{dex_0:02d}{dex_1:02d}{path}',
                'amount': self.amount_last.amount,
            }
        if len(self.trade_1.route.pools) == 1:
            data = arbitrage.encode_data32(
                dex_0, dex_1, self._amount_last_exp, self._amount_last_mant, self.route_0.token_out
            )
            return {'data': data}
        data = arbitrage.encode_data64(
            dex_0, dex_1, self._amount_last_exp, self._amount_last_mant, self.route_1.tokens[:-1]
        )
        return {'data': data}


def get_share_of_profit(params: dict):
    reduced_gas_share_pools = {
        '0xfC207DB720851f52545229E406068b205E02B952': 0.02,  # pcs xBLZD/WBNB
        '0xD9002B7E7d63A71F04a16840DA028e1cd534889D': 0.02,  # pcs2 xBLZD/WBNB
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
) -> list[PcsPcs2Pair]:
    return [
        PcsPcs2Pair(
            **params,
            contract=contract,
            gas_share_of_profit=get_share_of_profit(params),
            max_gas_multiplier=MAX_GAS_MULTIPLIER,
            w_swap_available=W_SWAP_AVAILABLE,
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
