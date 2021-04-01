import json

from core.entities import Token

from ..base import BaseClient
from .entities import UniV2Pair
from .uniswap_v2_dex import UniswapV2Dex


class PancakeswapClient(BaseClient):
    def __init__(
        self,
        caller_address: str,
        private_key: str,
        web3: str,
        tokens: list[Token] = None
    ):
        pancakeswap_dex = UniswapV2Dex(
            chain_id=56,
            addresses_filename='pancakeswap.json',
            fee=20
        )

        if tokens is None:
            tokens_data = json.load(open('addresses/tokens.json'))
            tokens = [Token(**data) for data in tokens_data]
        super().__init__(pancakeswap_dex, caller_address, private_key, web3, tokens=tokens)


__all__ = [
    'PancakeswapClient',
    'UniswapV2Dex',
    'UniV2Pair',
]
