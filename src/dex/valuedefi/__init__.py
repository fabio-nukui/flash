import json

from web3 import Web3

import tools

from .entities import ValueDefiPair
from .valuedefi_protocol import ValueDefiProtocol


class ValueDefiSwapDex(ValueDefiProtocol):
    def __init__(self, pairs_data: list[dict] = None, web3: Web3 = None):
        web3 = tools.w3.get_web3() if web3 is None else web3
        if pairs_data is None:
            with open('addresses/dex/valuedefiswap/valuedefiswap_default_pools.json') as f:
                pairs_data = json.load(f)['56']
        super().__init__(
            chain_id=56,
            addresses_filepath='addresses/dex/valuedefiswap/valuedefiswap.json',
            web3=web3,
            pairs_data=pairs_data
        )


__all__ = [
    'ValueDefiPair',
    'ValueDefiSwapDex',
]
