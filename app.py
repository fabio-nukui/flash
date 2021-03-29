import json
import time
from functools import partial
from pprint import pprint
from typing import Callable

from web3 import HTTPProvider, Web3
from web3._utils.filters import Filter
from web3.middleware import geth_poa_middleware

import configs
from dex.curve import CurvePool, EllipsisClient
from dex.uniswap_v2 import PancakeswapClient, UniV2Pair
from entities import Token, TokenAmount
from tools import cache


def get_updated_reserves(
    event,
    cake_pair: UniV2Pair,
    eps_pool: CurvePool
):
    pprint(event)
    data = {
        'cake': cake_pair.reserves,
        'eps': eps_pool.reserves
    }
    pprint(data)
    cache.clear_caches()


def log_loop(
    event_filter: Filter,
    event_handler: Callable,
):
    while True:
        for event in event_filter.get_new_entries():
            event_handler(event)

        time.sleep(configs.POLL_INTERVAL)


def main():
    web3 = Web3(HTTPProvider(configs.RCP_HTTPS_ENDPOINT))
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    tokens_data = json.load(open('addresses/tokens.json'))

    cake_client = PancakeswapClient(configs.ADDRESS, configs.PRIVATE_KEY, web3)
    eps_client = EllipsisClient(configs.ADDRESS, configs.PRIVATE_KEY, web3)

    token_amounts = [TokenAmount(Token(**d)) for d in tokens_data]
    cake_pair = UniV2Pair(
        token_amounts[0],
        token_amounts[1],
        cake_client.addresses['factory'],
        cake_client.addresses['init_code_hash'],
        cake_client.abis['IUniswapV2Pair'],
        web3,
    )

    event_handler = partial(
        get_updated_reserves,
        cake_pair=cake_pair,
        eps_pool=eps_client.pools['3pool'],
    )

    block_filter = web3.eth.filter('latest')
    log_loop(block_filter, event_handler)


if __name__ == '__main__':
    main()
