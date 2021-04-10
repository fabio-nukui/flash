import pathlib

from web3 import Web3

from core import Token, TokenAmount

from ..base import DexProtocol
from .entities import CurvePool, CurveTrade

ABI_DIRECTORY = pathlib.Path('abis/dex/curve')
POOL_ABI = ABI_DIRECTORY / 'IBasePool.json'
POOL_TOKEN_ABI = ABI_DIRECTORY / 'IPoolToken.json'
ZAP_ABI = ABI_DIRECTORY / 'IZap.json'


class CurveProtocol(DexProtocol):
    def __init__(
        self,
        chain_id: int,
        addresses_filepath: str,
        fee: int,
        web3: Web3,
        pool_names: list[str],
    ):
        self.pools: dict[str, CurvePool] = {}

        abi_filepaths = [POOL_ABI, POOL_TOKEN_ABI, ZAP_ABI]
        super().__init__(
            abi_filepaths,
            chain_id,
            addresses_filepath,
            web3,
            fee,
            pool_names=pool_names,
        )
        self.tokens = list({
            token
            for pool in self.pools.values()
            for token in pool.tokens
        })

    def _connect(self, pool_names: list[str] = None):
        for pool_name, addresses in self.addresses.items():
            if pool_names is not None and pool_name not in pool_names:
                continue
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

    def best_trade_exact_in(
        self,
        amoun_in: TokenAmount,
        token_out: Token,
        pool_names: list[str] = None
    ):
        if pool_names is None:
            pools = self.pools.values()
        else:
            pools = [self.pools[name] for name in pool_names]
        return CurveTrade.best_trade_exact_in(pools, amoun_in, token_out)
