import itertools
import logging

from web3 import Web3

from core.entities import Token, TokenAmount
from dex.base import Dex, DexProtocol

from .entities import UniV2Pair, UniV2Trade

FACTORY_ABI = 'IUniswapV2Factory.json'
ROUTER_ABI = 'IUniswapV2Router.json'
PAIR_ABI = 'IUniswapV2Pair.json'


class UniswapV2Dex(Dex):
    def __init__(self, chain_id: int, addresses_filename: str, fee: int):
        uniswapV2_protocol = DexProtocol(__file__, [FACTORY_ABI, ROUTER_ABI, PAIR_ABI])
        super().__init__(uniswapV2_protocol, chain_id, addresses_filename, fee)
        self.pairs: list[UniV2Pair] = []

    def connect(self, web3: Web3, tokens: list[Token]):
        self.web3 = web3
        self.tokens = tokens
        self.factory_contract = self.web3.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['factory']),
            abi=self.abis[FACTORY_ABI]
        )
        self.router_contract = self.web3.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['router']),
            abi=self.abis[ROUTER_ABI]
        )
        for token_1, token_2 in itertools.combinations(tokens, 2):
            amount_pair = (TokenAmount(token_1), TokenAmount(token_2))
            try:
                pair = UniV2Pair(
                    amount_pair,
                    self.addresses['factory'],
                    self.addresses['init_code_hash'],
                    self.abis[PAIR_ABI],
                    self.fee,
                    web3
                )
                if pair.reserves[0].amount > 0:
                    self.pairs.append(pair)
            except Exception as e:
                logging.exception(e)
                logging.warning(f'Failed to get data for UniswapV2 pair {token_1}/{token_2}')

    def best_trade_exact_out(self, token_in: Token, amount_out: TokenAmount, max_hops: int = 1):
        return UniV2Trade.best_trade_exact_out(self.pairs, token_in, amount_out, max_hops)
