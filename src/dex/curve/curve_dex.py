from core.entities import Token
from web3 import Web3

from dex.base import Dex, DexProtocol

from .entities import CurvePool

POOL_ABI = 'BasePool.json'
POOL_TOKEN_ABI = 'PoolToken.json'
ZAP_ABI = 'Zap.json'


class CurveDex(Dex):
    def __init__(self, chain_id: int, addresses_filename: str, fee: int):
        curve_protocol = DexProtocol(__file__, [POOL_ABI, POOL_TOKEN_ABI, ZAP_ABI])
        super().__init__(curve_protocol, chain_id, addresses_filename, fee)
        self.pools: dict[str, CurvePool] = {}

    def connect(self, web3: Web3):
        self.web3 = web3
        for pool_name, addresses in self.addresses.items():
            self.pools[pool_name] = CurvePool(
                pool_name,
                chain_id=self.chain_id,
                web3=self.web3,
                pool_address=addresses['pool'],
                pool_token_address=addresses['pool_token'],
                pool_abi=self.abis[POOL_ABI],
                pool_token_abi=self.abis[POOL_TOKEN_ABI],
                fee=self.fee,
            )
