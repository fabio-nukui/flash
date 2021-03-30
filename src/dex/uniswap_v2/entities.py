from __future__ import annotations

from copy import copy
from enum import Enum

from web3 import Web3

from core.entities import Token, TokenAmount
from tools.cache import ttl_cache


class TradeType(Enum):
    exact_in = 1
    exact_out = 2


class InsufficientLiquidity(Exception):
    pass


class UniV2Pair:
    def __init__(
        self,
        reserve_0: TokenAmount,
        reserve_1: TokenAmount,
        factory_address: str,
        init_code_hash: str,
        abi: dict,
        fee: int,
        provider: Web3
    ):
        self.reserve_0, self.reserve_1 = sorted([reserve_0, reserve_1])
        self.factory_address = factory_address
        self.init_code_hash = init_code_hash
        self.abi = abi
        self.fee = fee
        self.provider = provider

        self.tokens = (self.reserve_0.token, self.reserve_1.token)
        self.address = self._get_address()
        self.contract = self.provider.eth.contract(address=self.address, abi=self.abi)
        self.latest_transaction_timestamp = None

        if self.reserve_0.is_empty() or self.reserve_1.is_empty():
            self.update_amounts()

    def __repr__(self):
        return f'{self.__class__.__name__}' \
               f'({self.reserve_0.token.symbol}/{self.reserve_1.token.symbol})'

    def _get_address(self) -> str:
        """Return address of pair's liquidity pool"""
        encoded_tokens = Web3.solidityKeccak(
            ['address', 'address'], (self.reserve_0.token.address, self.reserve_1.token.address))

        prefix = Web3.toHex(hexstr='ff')
        raw = Web3.solidityKeccak(
            ['bytes', 'address', 'bytes', 'bytes'],
            [prefix, self.factory_address, encoded_tokens, self.init_code_hash]
        )
        return Web3.toChecksumAddress(raw.hex()[-40:])

    @property
    @ttl_cache
    def reserves(self) -> tuple[TokenAmount, TokenAmount]:
        self.update_amounts()
        return (self.reserve_0, self.reserve_1)

    def update_amounts(self):
        """Update the reserve amounts of both token pools and the unix timestamp of the latest
        transaction"""
        (
            self.reserve_0.amount,
            self.reserve_1.amount,
            self.latest_transaction_timestamp
        ) = self.contract.functions.getReserves().call()

    def price_of(self, token: Token) -> float:
        assert token in self.tokens, f'{token=} not in pair={self}'
        fee_impact = 10_000 / (10_000 - self.fee)
        if token == self.reserve_0.token:
            return self.reserve_1.amount / self.reserve_0.amount * fee_impact
        return self.reserve_0.amount / self.reserve_1.amount * fee_impact

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        assert amount_in in self.tokens
        assert amount_in.amount > 0
        if (
            self.reserve_0.amount == 0
            or self.reserve_1.amount == 0
        ):
            raise InsufficientLiquidity
        if amount_in.token == self.reserve_0.token:
            reserve_in = self.reserve_0
            reserve_out = self.reserve_1
        else:
            reserve_out = self.reserve_0
            reserve_in = self.reserve_1

        amount_in_with_fee = amount_in.amount * (10_000 - self.fee)
        numerator = amount_in_with_fee * reserve_out.amount
        denominator = reserve_in.amount * 10_000 + amount_in_with_fee

        return numerator // denominator

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        assert amount_out.token in self.tokens
        assert amount_out.amount > 0
        if amount_out.token == self.reserve_0.token:
            reserve_out = self.reserve_0
            reserve_in = self.reserve_1
        else:
            reserve_in = self.reserve_0
            reserve_out = self.reserve_1

        if (
            self.reserve_0.amount == 0
            or self.reserve_1.amount == 0
            or amount_out.amount >= reserve_out.amount
        ):
            raise InsufficientLiquidity

        numerator = reserve_in.amount * amount_out.amount * 10_000
        denominator = (reserve_out.amount - amount_out.amount) * (10_000 - self.fee)

        amount_in = numerator // denominator + 1
        return TokenAmount(reserve_in.token, amount_in)


class UniV2Route:
    def __init__(
        self,
        pairs: list[UniV2Pair],
        token_in: Token,
        token_out: Token,
    ):
        tokens = {token for pair in pairs for token in pair.tokens}
        assert token_in in tokens
        assert token_out in tokens
        self.pairs = pairs
        self.token_in = token_in
        self.token_out = token_out

    @property
    def symbols(self) -> str:
        symbol_list = [self.token_in.symbol]
        for pair in self.pairs:
            if symbol_list[-1] == pair.reserve_0.token.symbol:
                symbol_list.append(pair.reserve_1.token.symbol)
            else:
                symbol_list.append(pair.reserve_0.token.symbol)
        return '->'.join(symbol_list)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.symbols})'

    def mid_price(self) -> float:
        price = 1
        token_out = self.token_out
        for pair in reversed(self.pairs):
            price *= pair.price_of(token_out)
            if token_out == pair.reserve_0.token:
                token_out = pair.reserve_1.token
            else:
                token_out = pair.reserve_0.token
        return price


class InvalidRecursion(Exception):
    pass


class UniV2Trade:
    def __init__(self, route: UniV2Route, token_amount: TokenAmount, trade_type: TradeType):
        assert token_amount.amount > 0
        self.route = route
        self.token_amount = token_amount
        self.trade_type = trade_type

    def __repr__(self):
        str_amount = 'OUT: ' if self.trade_type == TradeType.exact_out else 'IN: '
        str_amount += f'{self.token_amount.token.symbol}:'
        str_amount += f'{self.token_amount.amount / 10 ** self.token_amount.token.decimals:,.2f}'
        return f'{self.__class__.__name__}({self.route.symbols}: {str_amount})'

    @staticmethod
    def exact_out(
        pairs: list[UniV2Pair],
        token_in: Token,
        amount_out: TokenAmount,
        max_hops: int = 1,
        current_pairs: list[UniV2Pair] = None,
        original_amount_out: TokenAmount = None,
        best_trades: list[UniV2Trade] = None
    ) -> UniV2Trade:
        """Return best trade given a list of liquidity pairs and an amount out

        Args:
            pairs (list[UniV2Pair]): List of possible liquidity pairs for route
            token_in (Token): Token to be traded in
            amount_out (TokenAmount): Exact amount to be traded out
            max_hops (int): Maximum number of hops
            current_pairs (List[UniV2Pair], optional): Used for recursion
            original_amount_out (TokenAmount, optional): Used for recursion
            best_trades (list[UniV2Trade], optional):  Used for recursion

        Returns:
            UniV2Trade: Trade that minimizes input amount
        """
        current_pairs = [] if current_pairs is None else current_pairs
        original_amount_out = amount_out if original_amount_out is None else original_amount_out
        best_trades = [] if best_trades is None else best_trades

        assert len(pairs) > 0, 'pairs must be positive number'
        assert max_hops > 0, 'max_hops must be positive number'

        for pair in pairs:
            if amount_out.token not in pair.tokens:
                continue
            try:
                amount_in = pair.get_amount_in(amount_out)
            except InsufficientLiquidity:
                continue
            if amount_in.token == token_in:
                route = UniV2Route([pair, *current_pairs], token_in, original_amount_out.token)
                trade = UniV2Trade(route, original_amount_out, TradeType.exact_out)
                best_trades.append(trade)
                best_trades.sort(key=lambda x: -x.token_amount.amount)
            elif max_hops > 1 and len(pairs) > 1:
                next_recursion_pairs = copy(pairs)
                next_recursion_pairs.remove(pair)
                UniV2Trade.exact_out(
                    pairs=next_recursion_pairs,
                    token_in=token_in,
                    amount_out=amount_in,
                    max_hops=max_hops - 1,
                    current_pairs=[pair, *current_pairs],
                    original_amount_out=original_amount_out,
                    best_trades=best_trades
                )
        return best_trades[0]
