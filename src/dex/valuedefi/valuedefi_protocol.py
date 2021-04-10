import logging
import pathlib

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
        pairs_data: list[dict],
    ):
        self.tokens: list[Token]
        self.pairs: list[ValueDefiPair] = []

        abi_filepaths = [FACTORY_ABI, PAIR_ABI]
        super().__init__(abi_filepaths, chain_id, addresses_filepath, web3, pairs_data=pairs_data)

    def _connect(self, pairs_data: list[dict]):
        for data in pairs_data:
            token_0 = Token(self.chain_id, data['token_0'], web3=self.web3)
            token_1 = Token(self.chain_id, data['token_1'], web3=self.web3)
            reserves = (TokenAmount(token_0), TokenAmount(token_1))
            pair = ValueDefiPair(
                reserves,
                self.abis[PAIR_ABI],
                data['fee'],
                self.web3,
                data['address'],
                data['token_0_weight'],
            )
            if pair.reserves[0] > 0:
                self.pairs.append(pair)
        self.tokens = list({token for pair in self.pairs for token in pair.tokens})
