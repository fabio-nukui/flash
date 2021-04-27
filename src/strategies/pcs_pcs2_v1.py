# Pancakeswap (PCS) x PancakeswapV2 (PCS2)

import logging

import configs
import tools
from arbitrage import ArbitragePairV1, PairManager
from arbitrage.arbitrage_pair_v1 import HighGasPriceStrategy
from dex import PancakeswapDex, PancakeswapDexV2

log = logging.getLogger(__name__)

# Strategy parameters
MAX_HOPS_FIRST_DEX = 1

# Estimations
GAS_COST_PCS1_FIRST_CHI_ON = 130_000
GAS_COST_PCS2_FIRST_CHI_ON = 130_000
GAS_INCREASE_WITH_HOP = 0.2908916690437962
GAS_SHARE_OF_PROFIT = 0.24
MAX_GAS_PRICE = 1_400 * 10 ** 9  # Around $100
MAX_GAS_MULTIPLIER = 7

# Created with notebooks/pcs_mdx_v1.ipynb (2021-04-22)
ADDRESS_DIRECTORY = 'strategy_files/pcs_pcs2_v1'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsPcs2V1.json'

# Optimization params
USE_FALLBACK = False


class PcsPcs2(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pools) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if type(self.first_dex) == PancakeswapDex:
            return int(GAS_COST_PCS1_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_PCS2_FIRST_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if type(self.first_dex) == PancakeswapDex:
            return self.contract.functions.swapPcs1First
        return self.contract.functions.swapPcs2First

    def _get_path_argument(self):
        return [t.address for t in self.first_trade.route.tokens]


def get_share_of_profit(params: dict):
    reduced_gas_share_pools = [
        '0xfC207DB720851f52545229E406068b205E02B952',  # pcs xBLZD/WBNB
        '0xD9002B7E7d63A71F04a16840DA028e1cd534889D',  # pcs2 xBLZD/WBNB
        # '0x3Ee4de968E47877F432226d6a9A0DAD6EAc6001b',  # pcs sALPACA/ALPACA
        # '0x6615187234104CE7d2fb1deF75eDb9d77408230D',  # pcs2 sALPACA/ALPACA
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
    optimization_params = {'use_fallback': USE_FALLBACK}
    dex_protocols = {
        'pcs_dex': PancakeswapDex,
        'pcs2_dex': PancakeswapDexV2,
    }
    dexes = PairManager.load_dex_protocols(ADDRESS_DIRECTORY, dex_protocols, web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        PcsPcs2(
            **params,
            contract=contract,
            gas_share_of_profit=get_share_of_profit(params),
            max_gas_price=MAX_GAS_PRICE,
            max_gas_multiplier=MAX_GAS_MULTIPLIER,
            high_gas_price_strategy=HighGasPriceStrategy.recalculate_at_max,
            optimization_params=optimization_params,
        )
        for params in PairManager.get_v1_pool_arguments(dexes.values(), web3, MAX_HOPS_FIRST_DEX)
    ]
    pair_manager = PairManager(ADDRESS_DIRECTORY, arbitrage_pairs, web3)
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        pair_manager.update_and_execute(block_number)
