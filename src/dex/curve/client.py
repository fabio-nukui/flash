from web3 import Web3

from entities import Token

from ..base.client_factory import DexClient, ProtocolFactory
from .entities import CurvePool

POOL_ABI = 'ICurve'
POOL_TOKEN_ABI = 'IPoolToken'
ZAP_ABI = 'IZap'


class CurveClient(DexClient):
    def __init__(self, address: str, private_key: str, provider: Web3):
        super().__init__(address, private_key, provider)

        self.pools = {}
        for pool_name, addresses in self.addresses.items():
            tokens = [
                Token(self.chain_id, address, provider=self.provider)
                for address in addresses['tokens']
            ]
            self.pools[pool_name] = CurvePool(
                pool_name,
                tokens,
                pool_address=addresses['pool'],
                pool_token_address=addresses['pool_token'],
                pool_abi=self.abis[POOL_ABI],
                pool_token_abi=self.abis[POOL_TOKEN_ABI],
                fee=self.swap_fee,
                provider=self.provider
            )


CurveProtocol = ProtocolFactory([POOL_ABI, POOL_TOKEN_ABI, ZAP_ABI], CurveClient, __file__)
