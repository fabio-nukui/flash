from web3 import Web3

from ..base import BaseClient
from .curve_dex import CurveDex
from .entities import CurvePool


class EllipsisClient(BaseClient):
    def __init__(self, caller_address: str, private_key: str, web3: Web3):
        ellipsis_dex = CurveDex(
            chain_id=56,
            addresses_filename='ellipsis.json',
            fee=4
        )
        super().__init__(ellipsis_dex, caller_address, private_key, web3)


__all__ = [
    'CurvePool',
    'CurveDex',
    'EllipsisClient',
]
