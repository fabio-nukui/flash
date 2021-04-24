import json

from web3 import Web3

import tools

from .entities import ValueDefiPair
from .valuedefi_protocol import ValueDefiProtocol


class ValueDefiSwapDex(ValueDefiProtocol):
    def __init__(
        self,
        pools_data: list[dict] = None,
        pools_addresses: list[str] = None,
        web3: Web3 = None,
        verbose_init: bool = False,
    ):
        web3 = tools.w3.get_web3() if web3 is None else web3
        addresses_filepath = 'addresses/dex/valuedefiswap/valuedefiswap.json'
        if pools_addresses is None and pools_data is None:
            with open('addresses/dex/valuedefiswap/valuedefiswap_default_pools.json') as f:
                pools_data = json.load(f)['56']
        super().__init__(
            chain_id=56,
            addresses_filepath=addresses_filepath,
            web3=web3,
            pools_addresses=pools_addresses,
            pools_data=pools_data,
            verbose_init=verbose_init,
        )


__all__ = [
    'ValueDefiPair',
    'ValueDefiSwapDex',
]
