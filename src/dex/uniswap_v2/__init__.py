import json
from typing import Union

from web3 import Web3

import tools
from core import Token

from .entities import UniV2Pair
from .uniswap_v2_protocol import UniswapV2Protocol


class PancakeswapDex(UniswapV2Protocol):
    def __init__(self, tokens: list[Union[dict, Token]] = None, web3: Web3 = None):
        web3 = tools.w3.get_web3() if web3 is None else web3
        if tokens is None:
            with open('addresses/dex/uniswap_v2/pancakeswap_default_tokens.json') as f:
                tokens_data = json.load(f)
            tokens = [Token(**data) for data in tokens_data]
        elif isinstance(tokens[0], dict):
            tokens = [Token(**data, web3=web3) for data in tokens]
        elif not isinstance(tokens[0], Token):
            raise ValueError(f"'tokens' must be a list of dict or Token, received {tokens}")

        super().__init__(
            chain_id=56,
            addresses_filepath='addresses/dex/uniswap_v2/pancakeswap.json',
            fee=20,
            web3=web3,
            tokens=tokens
        )


__all__ = [
    'PancakeswapDex',
    'UniV2Pair',
]
