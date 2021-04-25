# PancakeswapV2 (PCS2) x ValueDefiSwap (VDS)

import logging
from itertools import permutations
from typing import Iterable

import tools
import configs
from arbitrage import ArbitragePairV1, PairManager
from dex import PancakeswapDexV2, ValueDefiSwapDex


# Strategy parameters
MIN_ESTIMATED_PROFIT = 1
DISABLE_SAMPLE_SIZE = 50

# Gas-related parameters; data from notebooks/pcs_vds_analysis.ipynb (2021-04-20)
GAS_COST_PCS_FIRST_CHI_ON = 156_279.7
GAS_COST_VDS_FIRST_CHI_ON = 139_586.4
GAS_INCREASE_WITH_HOP = 0.266831606034439
MAX_GAS_PRICE = 11 * 10 ** 9
RAISE_AT_EXCESSIVE_GAS_PRICE = False
GAS_SHARE_OF_PROFIT = 0.24

# Created with notebooks/strategies/pcs2_vds_v1.ipynb (2021-04-25)
ADDRESS_DIRECTORY = 'strategy_files/pcs2_vds_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/Pcs2VdsV1.json'

log = logging.getLogger(__name__)


class PcsVdsPair(ArbitragePairV1):
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

    def _get_path_argument(self):
        if type(self.first_dex) == PancakeswapDexV2:
            return [
                self.second_trade.route.pools[0].address,
                *(t.address for t in self.first_trade.route.tokens)
            ]
        return [
            self.token_first.address,
            self.token_last.address,
            *(p.address for p in self.first_trade.route.pools)
        ]


def get_arbitrage_params(
    pcs2_dex: PancakeswapDexV2,
    vds_dex: ValueDefiSwapDex,
) -> Iterable[dict]:
    for dex_0, dex_1 in permutations([pcs2_dex, vds_dex]):
        for pool in dex_1.pools:
            for token_first, token_last in permutations(pool.tokens):
                yield {
                    'token_first': token_first,
                    'token_last': token_last,
                    'first_dex': dex_0,
                    'second_dex': dex_1,
                }


def run():
    web3 = tools.w3.get_web3(verbose=True)
    dex_protocols = {
        'pcs2_dex': PancakeswapDexV2,
        'vds_dex': ValueDefiSwapDex,
    }
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, dex_protocols, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        PcsVdsPair(
            contract=contract,
            web3=web3,
            gas_share_of_profit=GAS_SHARE_OF_PROFIT,
            max_gas_price=MAX_GAS_PRICE,
            raise_at_excessive_gas_price=RAISE_AT_EXCESSIVE_GAS_PRICE,
            **params,
        )
        for params in get_arbitrage_params(dexes['pcs2_dex'], dexes['vds_dex'])
    ]
    pair_manager = PairManager(
        ADDRESS_DIRECTORY,
        arbitrage_pairs,
        web3,
        MIN_ESTIMATED_PROFIT,
        DISABLE_SAMPLE_SIZE,
    )
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
