import itertools
import logging
import pathlib
from typing import Callable, Union

from web3 import Web3
from web3.contract import Contract

from core import Token, TokenAmount

from ..base import DexProtocol, TradePairsMixin
from .entities import UniV2Pair

ABI_DIRECTORY = pathlib.Path('abis/dex/uniswap_v2')
FACTORY_ABI = ABI_DIRECTORY / 'IUniswapV2FactoryMod.json'  # ABI modified to accept mdex fork
ROUTER_ABI = ABI_DIRECTORY / 'IUniswapV2Router.json'
PAIR_ABI = ABI_DIRECTORY / 'IUniswapV2Pair.json'

log = logging.getLogger(__name__)


class UniswapV2Protocol(DexProtocol, TradePairsMixin):
    def __init__(
        self,
        chain_id: int,
        addresses_filepath: str,
        fee: Union[int, Callable],
        web3: Web3,
        pools_addresses: list[str] = None,
        pools: list[UniV2Pair] = None,
        tokens: list[Token] = None,
        verbose_init: bool = False,
    ):
        self.pools: list[UniV2Pair] = []
        self.factory_contract: Contract
        self.router_contract: Contract

        abi_filepaths = [FACTORY_ABI, ROUTER_ABI, PAIR_ABI]

        if tokens is None and pools_addresses is None and pools is None:
            raise ValueError("None one of 'pools_addresses', 'tokens' or 'pools' were passed")
        super().__init__(
            abi_filepaths,
            chain_id,
            addresses_filepath,
            web3,
            fee,
            pools_addresses=pools_addresses,
            pools=pools,
            tokens=tokens,
            verbose_init=verbose_init,
        )

    def _connect(
        self,
        pools_addresses: list[str] = None,
        pools: list[UniV2Pair] = None,
        tokens: list[Token] = None,
        verbose_init: bool = False,
    ):
        self.factory_contract = self.web3.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['factory']),
            abi=self.abis[FACTORY_ABI]
        )
        self.router_contract = self.web3.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['router']),
            abi=self.abis[ROUTER_ABI]
        )
        if pools is not None:
            self.pools = pools
        elif pools_addresses is not None:
            if verbose_init:
                from tqdm import tqdm
                pools_addresses = tqdm(pools_addresses)
            for address in pools_addresses:
                try:
                    pool = UniV2Pair.from_address(
                        self.chain_id,
                        self.fee,
                        address,
                        self.abis[PAIR_ABI],
                        self.web3,
                    )
                    if pool.reserves[0] > 0:
                        self.pools.append(pool)
                except Exception as e:
                    log.info(f'Failed to load pair {address=} ({e})')
        else:
            for token_0, token_1 in itertools.combinations(tokens, 2):
                reserves = (TokenAmount(token_0), TokenAmount(token_1))
                try:
                    pool = UniV2Pair(
                        reserves,
                        self.fee,
                        self.abis[PAIR_ABI],
                        self.web3,
                        self.addresses['factory'],
                        self.addresses['init_code_hash'],
                    )
                    if pool.reserves[0] > 0:
                        self.pools.append(pool)
                except Exception as e:
                    log.info(f'Failed to get data for UniswapV2 pool {token_0}/{token_1} ({e})')
