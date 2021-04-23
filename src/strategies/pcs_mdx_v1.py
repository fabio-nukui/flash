# Pancakeswap (PCS) x ValueDefiSwap (VDS)

import json
import logging
from itertools import permutations
from typing import Iterable

import tools
import configs
from arbitrage import ArbitragePairV1
from dex import PancakeswapDex, MDex


# Strategy parameters
MIN_ESTIMATED_PROFIT = 1

# Based on notebooks/analysis/pcs_mdx_analysis_v1.ipynb (2021-04-23)
GAS_COST_PCS_FIRST_CHI_ON = 140_575.7
GAS_COST_MDX_FIRST_CHI_ON = 138_368.1
GAS_INCREASE_WITH_HOP = 0.2908916690437962

# Created with notebooks/pcs_mdx_v1.ipynb (2021-04-22)
ADDRESS_FILEPATH = 'addresses/strategies/pcs_mdx_v1.json'
CONTRACT_DATA_FILEPATH = 'deployed_contracts/PcsMdxV1.json'

log = logging.getLogger(__name__)


class PcsMdxPair(ArbitragePairV1):
    def _get_gas_cost(self) -> int:
        num_hops_extra_hops = len(self.first_trade.route.pairs) - 1
        gas_cost_multiplier = 1 + GAS_INCREASE_WITH_HOP * num_hops_extra_hops

        if isinstance(self.first_dex, PancakeswapDex):
            return int(GAS_COST_PCS_FIRST_CHI_ON * gas_cost_multiplier)
        else:
            return int(GAS_COST_MDX_FIRST_CHI_ON * gas_cost_multiplier)

    def _get_contract_function(self):
        if isinstance(self.first_dex, PancakeswapDex):
            return self.contract.functions.swapPcsFirst
        return self.contract.functions.swapMdxFirst

    def _get_path_argument(self):
        return [t.address for t in self.first_trade.route.tokens]


def get_arbitrage_params(
    pcs_dex: PancakeswapDex,
    mdx_dex: MDex,
) -> Iterable[dict]:
    for dex_0, dex_1 in permutations([pcs_dex, mdx_dex]):
        for pair in dex_1.pairs:
            for token_first, token_last in permutations(pair.tokens):
                yield {
                    'token_first': token_first,
                    'token_last': token_last,
                    'first_dex': dex_0,
                    'second_dex': dex_1,
                }


def run():
    web3 = tools.w3.get_web3(verbose=True)
    with open(ADDRESS_FILEPATH) as f:
        addresses = json.load(f)
        pcs_dex = PancakeswapDex(pairs_addresses=addresses['pcs_dex'], web3=web3)
        mdx_dex = MDex(pairs_addresses=addresses['mdx_dex'], web3=web3)
    contract = tools.transaction.load_contract(CONTRACT_DATA_FILEPATH)
    arbitrage_pairs = [
        PcsMdxPair(**params, contract=contract, web3=web3)
        for params in get_arbitrage_params(pcs_dex, mdx_dex)
    ]
    listener = tools.w3.BlockListener(web3)
    for block_number in listener.wait_for_new_blocks():
        configs.BLOCK = block_number
        tools.cache.clear_caches()
        running_tokens = set()
        for pair in arbitrage_pairs:
            if pair.is_running(block_number):
                for token in pair.first_trade.route.tokens + pair.second_trade.route.tokens:
                    running_tokens.add(token)
        next_round_pairs = [
            pair
            for pair in arbitrage_pairs
            if pair.token_first not in running_tokens and pair.token_last not in running_tokens
        ]
        if not next_round_pairs:
            continue
        for arb_pair in next_round_pairs:
            arb_pair.update_estimate(block_number)
        best_arbitrage = max(next_round_pairs, key=lambda x: x.estimated_net_result_usd)
        if best_arbitrage.estimated_net_result_usd > MIN_ESTIMATED_PROFIT:
            log.info(f'Arbitrage opportunity found on block {block_number}')
            if (current_block := web3.eth.block_number) != block_number:
                log.warning(
                    'Latest block advanced since beggining of iteration: '
                    f'{block_number=} vs {current_block=}'
                )
                continue
            best_arbitrage.execute()
