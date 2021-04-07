from web3 import Web3

import tools

from .curve_protocol import CurveProtocol
from .entities import CurvePool, CurveTrade


class EllipsisDex(CurveProtocol):
    def __init__(self, web3: Web3 = None):
        web3 = tools.w3.get_web3() if web3 is None else web3
        super().__init__(
            chain_id=56,
            addresses_filepath='addresses/dex/curve/ellipsis.json',
            fee=4,
            web3=web3,
        )


__all__ = [
    'CurvePool',
    'CurveTrade',
    'EllipsisDex',
]
