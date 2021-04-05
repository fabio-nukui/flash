import json

from core.entities import Token

from .entities import UniV2Pair, UniV2Trade
from .uniswap_v2_protocol import UniswapV2Protocol


class PancakeswapDex(UniswapV2Protocol):
    def __init__(self, web3: str, tokens: list[Token] = None):
        if tokens is None:
            tokens_data = json.load(open('addresses/tokens.json'))
            tokens = [Token(**data) for data in tokens_data]

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
