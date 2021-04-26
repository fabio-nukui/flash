from __future__ import annotations

import logging
from copy import copy

from web3.contract import Contract

import configs
from exceptions import InsufficientLiquidity

from .base import LiquidityPool, Route, Token, TokenAmount, TradePools

log = logging.getLogger(__name__)


class LiquidityPair(LiquidityPool):
    def __init__(self, reserves: tuple[TokenAmount, TokenAmount], fee: int, *, contract: Contract):
        """Abstract class representing all liquidity pools with 2 different assets"""
        # Follow Uniswap convension of tokens sorted by address
        self._reserve_0, self._reserve_1 = sorted(reserves, key=lambda x: x.token)
        super().__init__(
            fee,
            tokens=(self._reserve_0.token, self._reserve_1.token),
            contract=contract
        )

        if self._reserve_0.is_empty() or self._reserve_1.is_empty():
            self._update_amounts()

    def __repr__(self):
        return f'{self.__class__.__name__}({self._reserve_0.symbol}/{self._reserve_1.symbol})'

    def _get_in_out_reserves(
        self,
        amount_in: TokenAmount = None,
        amount_out: TokenAmount = None
    ) -> tuple[TokenAmount, TokenAmount]:
        """Given an amount in and/or an amount out, checks for insuficient liquidity and return
        the reserves pair in order reserve_in, reserve_out"""
        assert amount_in is not None or amount_out is not None, \
            'At least one of token_in or token_out must be passed'
        assert amount_in is None or amount_in.token in self.tokens, 'amount_in not in pair'
        assert amount_out is None or amount_out.token in self.tokens, 'amount_out not in pair'

        if self.reserves[0] == 0 or self.reserves[1] == 0:
            raise InsufficientLiquidity
        if amount_in is None:
            token_in = self.tokens[0] if amount_out.token == self.tokens[1] else self.tokens[1]
        else:
            token_in = amount_in.token

        if token_in == self.tokens[0]:
            reserve_in, reserve_out = self.reserves
        else:
            reserve_out, reserve_in = self.reserves
        if amount_out is not None and amount_out >= reserve_out:
            raise InsufficientLiquidity
        return reserve_in, reserve_out

    @property
    def reserves(self) -> tuple[TokenAmount, TokenAmount]:
        if not configs.STOP_RESERVE_UPDATE:
            self._update_amounts()
        return (self._reserve_0, self._reserve_1)

    def apply_transactions(self, amounts: list[TokenAmount]):
        for amount in amounts:
            if amount.token == self._reserve_0.token:
                self._reserve_0 += amount
            elif amount.token == self._reserve_1.token:
                self._reserve_1 += amount
            else:
                raise ValueError("'amounts' must have same tokens as reserves")

    def _update_amounts(self):
        """Update the reserve amounts of both token pools and the unix timestamp of the latest
        transaction"""
        (
            self._reserve_0.amount,
            self._reserve_1.amount,
            self.latest_transaction_timestamp
        ) = self._get_reserves()

    def _get_reserves(self):
        raise NotImplementedError

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        """Get amount of tokens out given exact amount in.
            This is the default constant product AMM implementation, override in subclass if needed.
        """
        reserve_in, reserve_out = self._get_in_out_reserves(amount_in=amount_in)

        amount_in_with_fee = amount_in.amount * (10_000 - self.fee)
        numerator = amount_in_with_fee * reserve_out.amount
        denominator = reserve_in.amount * 10_000 + amount_in_with_fee

        amount_out = numerator // denominator
        return TokenAmount(reserve_out.token, amount_out)

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        """Get amount of tokens out given exact amount in.
            This is the default constant product AMM implementation, override in subclass if needed.
        """
        reserve_in, reserve_out = self._get_in_out_reserves(amount_out=amount_out)
        numerator = reserve_in.amount * amount_out.amount * 10_000
        denominator = (reserve_out.amount - amount_out.amount) * (10_000 - self.fee)

        amount_in = numerator // denominator + 1
        return TokenAmount(reserve_in.token, amount_in)


class RoutePairs(Route):
    def __init__(
        self,
        pools: list[LiquidityPair],
        token_in: Token,
        token_out: Token,
    ):
        """Route of liquidity pairs, use to compute trade with in/out amounts"""
        self.pools: LiquidityPair

        super().__init__(pools, token_in, token_out)
        self.tokens = self._get_tokens()

    def _get_tokens(self) -> list[Token]:
        tokens = [self.token_in]
        for pair in self.pools:
            if tokens[-1] == pair.tokens[0]:
                tokens.append(pair.tokens[1])
            else:
                tokens.append(pair.tokens[0])
        return tokens

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        for pool in self.pools:
            # amount_out of each iteration is amount_in of next one
            amount_in = pool.get_amount_out(amount_in)
        return amount_in

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        for pool in reversed(self.pools):
            # amount_in of each iteration is amount_out of next one
            amount_out = pool.get_amount_in(amount_out)
        return amount_out


class TradePairs(TradePools):
    def __init__(
        self,
        amount_in: TokenAmount,
        amount_out: TokenAmount,
        route: RoutePairs,
        max_slippage: int = None
    ):
        """Trade involving a sequence of liquidity pools"""
        self.route = route
        super().__init__(amount_in, amount_out, max_slippage)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.route.symbols}: {self._str_in_out})'

    @classmethod
    def best_trade_exact_in(
        cls,
        pools: list[LiquidityPair],
        amount_in: TokenAmount,
        token_out: Token,
        max_hops: int = 1,
        hop_penalty: float = None,
        max_slippage: int = None,
    ) -> TradePairs:
        trades = cls.trades_exact_in(
            pools,
            amount_in,
            token_out,
            max_hops,
            hop_penalty,
            max_slippage,
        )
        if not trades:
            raise InsufficientLiquidity('No route with suficient liquidity')
        return max(trades, key=lambda x: x.amount_out)

    @staticmethod
    def trades_exact_in(
        pools: list[LiquidityPair],
        amount_in: TokenAmount,
        token_out: Token,
        max_hops: int = 1,
        hop_penalty: float = None,
        max_slippage: int = None,
        current_pools: list[LiquidityPair] = None,
        original_amount_in: TokenAmount = None,
        best_trades: list[TradePairs] = None
    ) -> TradePairs:
        """Return possible trades given a list of liquidity pools and an amount in

        Args:
            pools (list[LiquidityPair]): List of possible liquidity pools for route
            amount_in (TokenAmount): Exact amount to be traded in
            token_out (Token): Token to be traded out
            max_hops (int): Maximum number of hops
            hop_penalty (float, optional): Penalty % on additional hops to account for higher gas
            max_slippage (int): Maximum slippage in basis points
            current_pools (List[LiquidityPair], optional): Used for recursion
            original_amount_in (TokenAmount, optional): Used for recursion
            best_trades (list[TradePairs], optional):  Used for recursion

        Returns:
            TradePairs: Trade that maximizes output amount
        """
        current_pools = [] if current_pools is None else current_pools
        original_amount_in = amount_in if original_amount_in is None else original_amount_in
        best_trades = [] if best_trades is None else best_trades

        assert len(pools) > 0, 'at least one pair must be given'
        assert max_hops > 0, 'max_hops must be positive number'

        for pool in pools:
            if amount_in.token not in pool.tokens:
                continue
            try:
                amount_out = pool.get_amount_out(amount_in)
            except InsufficientLiquidity:
                continue
            if amount_out.token == token_out:
                # End of recursion
                route = RoutePairs(
                    [*current_pools, pool],
                    original_amount_in.token,
                    token_out,
                    hop_penalty=hop_penalty,
                )
                trade = TradePairs(
                    route=route,
                    amount_in=original_amount_in,
                    amount_out=TokenAmount(token_out),
                    max_slippage=max_slippage
                )
                best_trades.append(trade)
            elif max_hops > 1 and len(pools) > 1:
                next_recursion_pools = copy(pools)
                next_recursion_pools.remove(pool)
                TradePairs.trades_exact_in(
                    pools=next_recursion_pools,
                    amount_in=amount_out,  # Amount in of next recursion is current amount_out
                    token_out=token_out,
                    max_hops=max_hops - 1,
                    hop_penalty=hop_penalty,
                    max_slippage=max_slippage,
                    current_pools=[*current_pools, pool],
                    original_amount_in=original_amount_in,
                    best_trades=best_trades
                )
        return best_trades

    @classmethod
    def best_trade_exact_out(
        cls,
        pools: list[LiquidityPair],
        token_in: Token,
        amount_out: TokenAmount,
        max_hops: int = 1,
        hop_penalty: float = None,
        max_slippage: int = None,
    ) -> TradePairs:
        trades = cls.trades_exact_out(
            pools,
            token_in,
            amount_out,
            max_hops,
            hop_penalty,
            max_slippage,
        )
        if not trades:
            raise InsufficientLiquidity('No route with suficient liquidity')
        return min(trades, key=lambda x: x.amount_in)

    @staticmethod
    def trades_exact_out(
        pools: list[LiquidityPair],
        token_in: Token,
        amount_out: TokenAmount,
        max_hops: int = 1,
        hop_penalty: float = None,
        max_slippage: int = None,
        current_pools: list[LiquidityPair] = None,
        original_amount_out: TokenAmount = None,
        best_trades: list[TradePairs] = None
    ) -> list[TradePairs]:
        """Return possible trades given a list of liquidity pools and an amount out

        Args:
            pools (list[LiquidityPair]): List of possible liquidity pools for route
            token_in (Token): Token to be traded in
            amount_out (TokenAmount): Exact amount to be traded out
            max_hops (int): Maximum number of hops
            hop_penalty (float, optional): Penalty on additional hops
            max_slippage (int): Maximum slippage in basis points
            current_pools (List[LiquidityPair], optional): Used for recursion
            original_amount_out (TokenAmount, optional): Used for recursion
            best_trades (list[TradePairs], optional):  Used for recursion

        Returns:
            TradePairs: Trade that minimizes input amount
        """
        current_pools = [] if current_pools is None else current_pools
        original_amount_out = amount_out if original_amount_out is None else original_amount_out
        best_trades = [] if best_trades is None else best_trades

        assert len(pools) > 0, 'at least one pool must be given'
        assert max_hops > 0, 'max_hops must be positive number'

        for pool in pools:
            if amount_out.token not in pool.tokens:
                continue
            try:
                amount_in = pool.get_amount_in(amount_out)
            except InsufficientLiquidity:
                continue
            if amount_in.token == token_in:
                # End of recursion
                route = RoutePairs(
                    [pool, *current_pools],
                    token_in,
                    original_amount_out.token,
                    hop_penalty,
                )
                trade = TradePairs(
                    route=route,
                    amount_in=TokenAmount(token_in),
                    amount_out=original_amount_out,
                    max_slippage=max_slippage
                )
                best_trades.append(trade)
            elif max_hops > 1 and len(pools) > 1:
                next_recursion_pools = copy(pools)
                next_recursion_pools.remove(pool)
                TradePairs.trades_exact_out(
                    pools=next_recursion_pools,
                    token_in=token_in,
                    amount_out=amount_in,  # Amount out of next recursion is current amount_in
                    max_hops=max_hops - 1,
                    hop_penalty=hop_penalty,
                    max_slippage=max_slippage,
                    current_pools=[pool, *current_pools],
                    original_amount_out=original_amount_out,
                    best_trades=best_trades
                )
        return best_trades
