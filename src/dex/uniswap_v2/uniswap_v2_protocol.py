import itertools
import logging
import pathlib

from web3 import Web3

from core.entities import Token, TokenAmount

from ..base import DexProtocol
from .entities import UniV2Pair, UniV2Trade
from .valuedefiswap_entities import ValueDefiPair

ABI_DIRECTORY = pathlib.Path('abis/dex/uniswap_v2')
FACTORY_ABI = ABI_DIRECTORY / 'IUniswapV2Factory.json'
ROUTER_ABI = ABI_DIRECTORY / 'IUniswapV2Router.json'
PAIR_ABI = ABI_DIRECTORY / 'IUniswapV2Pair.json'

log = logging.getLogger(__name__)


class UniswapV2Protocol(DexProtocol):
    def __init__(
        self,
        chain_id: int,
        addresses_filepath: str,
        fee: int,
        web3: Web3,
        tokens: list[Token],
    ):
        self.pairs: list[UniV2Pair] = []

        abi_filepaths = [FACTORY_ABI, ROUTER_ABI, PAIR_ABI]
        super().__init__(abi_filepaths, chain_id, addresses_filepath, web3, fee, tokens=tokens)

    def _connect(self, tokens: list[Token]):
        self.tokens = tokens
        self.factory_contract = self.web3.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['factory']),
            abi=self.abis[FACTORY_ABI]
        )
        self.router_contract = self.web3.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['router']),
            abi=self.abis[ROUTER_ABI]
        )
        for token_0, token_1 in itertools.combinations(tokens, 2):
            amount_pair = (TokenAmount(token_0), TokenAmount(token_1))
            try:
                pair = UniV2Pair(
                    amount_pair,
                    self.addresses['factory'],
                    self.addresses['init_code_hash'],
                    self.abis[PAIR_ABI],
                    self.fee,
                    self.web3,
                )
                if pair.reserves[0] > 0:
                    self.pairs.append(pair)
            except Exception as e:
                log.exception(e)
                log.warning(f'Failed to get data for UniswapV2 pair {token_0}/{token_1}')

    def best_trade_exact_out(self, token_in: Token, amount_out: TokenAmount, max_hops: int = 1):
        return UniV2Trade.best_trade_exact_out(self.pairs, token_in, amount_out, max_hops)


class ValueDefiProtocol(UniswapV2Protocol):
    def __init__(
        self,
        chain_id: int,
        addresses_filepath: str,
        web3: Web3,
        pairs_data: list[dict],
    ):
        self.pairs: list[ValueDefiPair] = []

        abi_filepaths = [FACTORY_ABI, ROUTER_ABI, PAIR_ABI]
        super().__init__(abi_filepaths, chain_id, addresses_filepath, web3, pairs_data=pairs_data)

    def _connect(self, pairs_data: list[dict]):
        for data in pairs_data:
            amount_pair = (TokenAmount(data['token_0']), TokenAmount(data['token_1']))
            pair = ValueDefiPair(
                amount_pair,
                data['address'],
                data['token_0_weight'],
                self.abis[PAIR_ABI],
                data['fee'],
                self.web3,
            )
            if pair.reserves[0] > 0:
                self.pairs.append(pair)
