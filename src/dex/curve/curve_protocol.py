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
        self.pools: list[CurvePool]

        abi_filepaths = [POOL_ABI, POOL_TOKEN_ABI, ZAP_ABI]
        super().__init__(
            abi_filepaths,
            chain_id,
            addresses_filepath,
            web3,
            fee,
            pool_names=pool_names,
        )

    def _connect(self, pool_names: list[str] = None):
        for pool_name, addresses in self.addresses.items():
            if pool_names is not None and pool_name not in pool_names:
                continue
            self.pools.append(
                CurvePool(
                    pool_name,
                    chain_id=self.chain_id,
                    web3=self.web3,
                    pool_address=addresses['pool'],
                    pool_token_address=addresses['pool_token'],
                    pool_abi=self.abis[POOL_ABI],
                    pool_token_abi=self.abis[POOL_TOKEN_ABI],
                    fee=self.fee,
                )
            )

    def best_trade_exact_in(
        self,
        amoun_in: TokenAmount,
        token_out: Token,
        pool_names: list[str] = None
    ):
        return CurveTrade.best_trade_exact_in(self.pools, amoun_in, token_out)
