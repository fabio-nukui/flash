from .client import UniswapV2Protocol, UniswapV2Client
from .entities import UniV2Pair, UniV2Route

PancakeswapClient: UniswapV2Client = UniswapV2Protocol(
    class_name='PancakeswapClient',
    dex_name='pancakeswap',
    chain_id=56,
    swap_fee=20
)

__all__ = [
    'PancakeswapClient',
    'UniV2Pair',
    'UniV2Route',
]
