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
FACTORY_ABI = ABI_DIRECTORY / 'IUniswapV2Factory.json'
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
        pairs_addresses: list[str] = None,
        tokens: list[Token] = None,
        verbose_init: bool = False,
    ):
        self.tokens: list[Token]
        self.pairs: list[UniV2Pair] = []
        self.factory_contract: Contract
        self.router_contract: Contract

        abi_filepaths = [FACTORY_ABI, ROUTER_ABI, PAIR_ABI]

        if tokens is None and pairs_addresses is None:
            raise ValueError("None one of 'pairs_addresses' or 'tokens' were passed")
        super().__init__(
            abi_filepaths,
            chain_id,
            addresses_filepath,
            web3,
            fee,
            pairs_addresses=pairs_addresses,
            tokens=tokens,
            verbose_init=verbose_init,
        )

    def _connect(
        self,
        pairs_addresses: list[str] = None,
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
        if pairs_addresses is not None:
            if verbose_init:
                from tqdm import tqdm
                pairs_addresses = tqdm(pairs_addresses)
            for address in pairs_addresses:
                try:
                    pair = UniV2Pair.from_address(
                        self.chain_id,
                        self.fee,
                        address,
                        self.abis[PAIR_ABI],
                        self.web3,
                    )
                    if pair.reserves[0] > 0:
                        self.pairs.append(pair)
                except Exception as e:
                    log.info(f'Failed to load pair {address=} ({e})')
        else:
            for token_0, token_1 in itertools.combinations(tokens, 2):
                reserves = (TokenAmount(token_0), TokenAmount(token_1))
                try:
                    pair = UniV2Pair(
                        reserves,
                        self.fee,
                        self.abis[PAIR_ABI],
                        self.web3,
                        self.addresses['factory'],
                        self.addresses['init_code_hash'],
                    )
                    if pair.reserves[0] > 0:
                        self.pairs.append(pair)
                except Exception as e:
                    log.info(f'Failed to get data for UniswapV2 pair {token_0}/{token_1} ({e})')
        self.tokens = list({token for pair in self.pairs for token in pair.tokens})
