import logging
import pathlib

from web3.contract import Contract
from web3 import Web3

from core import Token, TokenAmount

from ..base import DexProtocol, TradePairsMixin
from .entities import ValueDefiPair

ABI_DIRECTORY = pathlib.Path('abis/dex/valuedefi')

PAIR_ABI = ABI_DIRECTORY / 'IValueLiquidPair.json'
FACTORY_ABI = ABI_DIRECTORY / 'IValueLiquidFactory.json'

log = logging.getLogger(__name__)


class ValueDefiProtocol(DexProtocol, TradePairsMixin):
    def __init__(
        self,
        chain_id: int,
        addresses_filepath: str,
        web3: Web3,
        pools_addresses: list[str] = None,
        pairs_data: list[dict] = None,
        verbose_init: bool = False,
    ):
        self.tokens: list[Token]
        self.pairs: list[ValueDefiPair] = []
        self.factory_contract: Contract

        abi_filepaths = [FACTORY_ABI, PAIR_ABI]

        if pools_addresses is None and pairs_data is None:
            raise ValueError("None one of 'pools_addresses' or 'pairs_data' were passed")
        super().__init__(
            abi_filepaths,
            chain_id,
            addresses_filepath,
            web3,
            pairs_data=pairs_data,
            pools_addresses=pools_addresses,
            verbose_init=verbose_init,
        )

    def _connect(
        self,
        pools_addresses: list[str],
        pairs_data: list[dict],
        verbose_init: bool = False,
    ):
        self.factory_contract = self.web3.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['factory']),
            abi=self.abis[FACTORY_ABI]
        )
        if pools_addresses is not None:
            if verbose_init:
                from tqdm import tqdm
                pools_addresses = tqdm(pools_addresses)
            for address in pools_addresses:
                try:
                    pair = ValueDefiPair.from_address(
                        self.chain_id,
                        address,
                        self.abis[PAIR_ABI],
                        self.web3,
                    )
                    if pair.reserves[0] > 0:
                        self.pairs.append(pair)
                except Exception as e:
                    log.info(f'Failed to load pair {address=} ({e})')
        else:
            for data in pairs_data:
                token_0 = Token(self.chain_id, data['token_0'], web3=self.web3)
                token_1 = Token(self.chain_id, data['token_1'], web3=self.web3)
                reserves = (TokenAmount(token_0), TokenAmount(token_1))
                try:
                    pair = ValueDefiPair(
                        reserves,
                        data['fee'],
                        tuple(data['weights']),
                        data['address'],
                        self.abis[PAIR_ABI],
                        self.web3,
                    )
                    if pair.reserves[0] > 0:
                        self.pairs.append(pair)
                except Exception as e:
                    log.info(f'Failed to get data for ValueDefi pair {token_0}/{token_1} ({e})')
        self.tokens = list({token for pair in self.pairs for token in pair.tokens})
