from __future__ import annotations

from copy import copy

from web3 import Web3

from core.entities import Price, Token, TokenAmount, Trade
from tools.cache import ttl_cache


class InsufficientLiquidity(Exception):
    pass


class UniV2Pair:
    def __init__(
        self,
        reserves: tuple[TokenAmount, TokenAmount],
        factory_address: str,
        init_code_hash: str,
        abi: dict,
        fee: int,
        web3: Web3
    ):
        self._reserve_0, self._reserve_1 = sorted(reserves, key=lambda x: x.token)
        self.factory_address = factory_address
        self.init_code_hash = init_code_hash
        self.abi = abi
        self.fee = fee
        self.web3 = web3

        self.tokens = (self._reserve_0.token, self._reserve_1.token)
        self.address = self._get_address()
        self.contract = self.web3.eth.contract(address=self.address, abi=self.abi)
        self.latest_transaction_timestamp = None

        if self._reserve_0.is_empty() or self._reserve_1.is_empty():
            self._update_amounts()

    def __repr__(self):
        return f'{self.__class__.__name__}' \
               f'({self._reserve_0.symbol}/{self._reserve_1.symbol})'

    def _get_address(self) -> str:
        """Return address of pair's liquidity pool"""
        encoded_tokens = Web3.solidityKeccak(
            ['address', 'address'], (self._reserve_0.token.address, self._reserve_1.token.address))

        prefix = Web3.toHex(hexstr='ff')
        raw = Web3.solidityKeccak(
            ['bytes', 'address', 'bytes', 'bytes'],
            [prefix, self.factory_address, encoded_tokens, self.init_code_hash]
        )
        return Web3.toChecksumAddress(raw.hex()[-40:])

    @property
    def reserves(self) -> tuple[TokenAmount, TokenAmount]:
        self._update_amounts()
        return (self._reserve_0, self._reserve_1)

    @ttl_cache
    def _get_reserves(self):
        return self.contract.functions.getReserves().call()

    def _update_amounts(self):
        """Update the reserve amounts of both token pools and the unix timestamp of the latest
        transaction"""
        (
            self._reserve_0.amount,
            self._reserve_1.amount,
            self.latest_transaction_timestamp
        ) = self._get_reserves()

    def price_of(self, token: Token) -> Price:
        assert token in self.tokens, f'{token=} not in pair={self}'
        fee_impact = 10_000 / (10_000 - self.fee)
        if token == self.reserves[0].token:
            return self.reserves[1] / self.reserves[0] * fee_impact
        return self.reserves[0] / self.reserves[1] * fee_impact

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        assert amount_in.token in self.tokens
        if (
            self.reserves[0].amount == 0
            or self.reserves[1].amount == 0
        ):
            raise InsufficientLiquidity
        if amount_in.token == self.reserves[0].token:
            reserve_in = self.reserves[0]
            reserve_out = self.reserves[1]
        else:
            reserve_out = self.reserves[0]
            reserve_in = self.reserves[1]

        amount_in_with_fee = amount_in.amount * (10_000 - self.fee)
        numerator = amount_in_with_fee * reserve_out.amount
        denominator = reserve_in.amount * 10_000 + amount_in_with_fee

        amount_out = numerator // denominator
        return TokenAmount(reserve_out.token, amount_out)

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        assert amount_out.token in self.tokens
        if amount_out.token == self.reserves[0].token:
            reserve_out = self.reserves[0]
            reserve_in = self.reserves[1]
        else:
            reserve_in = self.reserves[0]
            reserve_out = self.reserves[1]

        if (
            self.reserves[0].amount == 0
            or self.reserves[1].amount == 0
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
            if symbol_list[-1] == pair.tokens[0].symbol:
                symbol_list.append(pair.tokens[1].symbol)
            else:
                symbol_list.append(pair.tokens[0].symbol)
        return '->'.join(symbol_list)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.symbols})'

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        for pair in self.pairs:
            # amount_out of each iteration is amount_in of next one
            amount_in = pair.get_amount_out(amount_in)
        return amount_in

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        for pair in reversed(self.pairs):
            # amount_in of each iteration is amount_out of next one
            amount_out = pair.get_amount_in(amount_out)
        return amount_out


class InvalidRecursion(Exception):
    pass


class UniV2Trade(Trade):
    def __init__(
        self,
        route: UniV2Route,
        amount_in: TokenAmount = None,
        amount_out: TokenAmount = None,
        max_slippage: int = None,
    ):
        self.route = route
        super().__init__(amount_in, amount_out, max_slippage)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.route.symbols}: {self._str_in_out})'

    def _get_amount_in(self) -> TokenAmount:
        return self.route.get_amount_in(self.amount_out)

    def _get_amount_out(self) -> TokenAmount:
        return self.route.get_amount_out(self.amount_in)

    @staticmethod
    def best_trade_exact_out(
        pairs: list[UniV2Pair],
        token_in: Token,
        amount_out: TokenAmount,
        max_hops: int = 1,
        max_slippage: int = None,
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
            max_slippage (int): Maximum slippage in basis points
            current_pairs (List[UniV2Pair], optional): Used for recursion
            original_amount_out (TokenAmount, optional): Used for recursion
            best_trades (list[UniV2Trade], optional):  Used for recursion

        Returns:
            UniV2Trade: Trade that minimizes input amount
        """
        current_pairs = [] if current_pairs is None else current_pairs
        original_amount_out = amount_out if original_amount_out is None else original_amount_out
        best_trades = [] if best_trades is None else best_trades

        assert len(pairs) > 0, 'at least one pair must be given'
        assert max_hops > 0, 'max_hops must be positive number'

        for pair in pairs:
            if amount_out.token not in pair.tokens:
                continue
            try:
                amount_in = pair.get_amount_in(amount_out)
            except InsufficientLiquidity:
                continue
            if amount_in.token == token_in:
                # End of recursion
                route = UniV2Route([pair, *current_pairs], token_in, original_amount_out.token)
                trade = UniV2Trade(
                    route=route,
                    amount_in=TokenAmount(token_in),
                    amount_out=original_amount_out,
                    max_slippage=max_slippage
                )
                best_trades.append(trade)
            elif max_hops > 1 and len(pairs) > 1:
                next_recursion_pairs = copy(pairs)
                next_recursion_pairs.remove(pair)
                UniV2Trade.best_trade_exact_out(
                    pairs=next_recursion_pairs,
                    token_in=token_in,
                    amount_out=amount_in,  # Amount out of next recursion is current amount_in
                    max_hops=max_hops - 1,
                    max_slippage=max_slippage,
                    current_pairs=[pair, *current_pairs],
                    original_amount_out=original_amount_out,
                    best_trades=best_trades
                )
        return min(best_trades, key=lambda x: x.amount_in)
