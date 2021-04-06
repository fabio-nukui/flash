import json
from typing import Union

from web3 import Web3

from core.entities import Token
from tools import web3_tools

from .entities import UniV2Pair, UniV2Trade
from .uniswap_v2_protocol import UniswapV2Protocol


class PancakeswapDex(UniswapV2Protocol):
    def __init__(self, web3: Web3 = None, tokens: list[Union[dict, Token]] = None):
        web3 = web3_tools.get_web3() if web3 is None else web3
        if tokens is None:
            tokens_data = json.load(open('addresses/tokens.json'))
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
    'PancakeswapClient',
    'UniswapV2Dex',
    'UniV2Pair',
    'UniV2Trade',
]
