from __future__ import annotations

import logging
from copy import copy
from typing import Union

from web3.contract import Contract

from exceptions import InsufficientLiquidity

from .base import LiquidityPool, Route, Token, TokenAmount, TradePools, TradeType

log = logging.getLogger(__name__)


class LiquidityPair(LiquidityPool):
    def __init__(self, reserves: tuple[TokenAmount, TokenAmount], fee: int, *, contract: Contract):
        """Abstract class representing all liquidity pools with 2 different assets"""
        # Follow Uniswap convension of tokens sorted by address
        reserves = sorted(reserves, key=lambda x: x.token)
        super().__init__(fee, reserves, contract)

    def __repr__(self):
        return f'{self.__class__.__name__}({self._reserves[0].symbol}/{self._reserves[1].symbol})'

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

    def _update_amounts(self):
        """Update the reserve amounts of both token pools and the unix timestamp of the latest
        transaction"""
        (
            self._reserves[0].amount,
            self._reserves[1].amount,
            self.latest_transaction_timestamp
        ) = self._get_reserves()

    def _get_reserves(self):
        raise NotImplementedError

    def get_amount_out(self, amount_in: TokenAmount, token_out: Token = None) -> TokenAmount:
        """Get amount of tokens out given exact amount in.
            This is the default constant product AMM implementation, override in subclass if needed.
        """
        if token_out is not None:
            assert token_out in self.tokens and token_out != amount_in.token
        return self._get_amount_out(amount_in)

    def _get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        reserve_in, reserve_out = self._get_in_out_reserves(amount_in=amount_in)

        amount_in_with_fee = amount_in.amount * (10_000 - self.fee)
        numerator = amount_in_with_fee * reserve_out.amount
        denominator = reserve_in.amount * 10_000 + amount_in_with_fee

        amount_out = numerator // denominator
        return TokenAmount(reserve_out.token, amount_out)

    def get_amount_in(
        self,
        arg_0: Union[Token, TokenAmount],
        arg_1: TokenAmount = None
    ) -> TokenAmount:
        """Get amount of tokens out given exact amount in.
            This is the default constant product AMM implementation, override in subclass if needed.
        """
        if arg_1 is None:
            assert isinstance(arg_0, TokenAmount)
            return self._get_amount_in(arg_0)  # arg_0 is amount_out
        assert isinstance(arg_0, Token) and isinstance(arg_1, TokenAmount)
        # arg_0 is token_in and arg_1 is amount_out  # noqa: E501
        assert arg_0 in self.tokens and arg_0 != arg_1.token
        return self._get_amount_in(arg_1)

    def _get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
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

        tokens = [token_in]
        for pair in pools:
            if tokens[-1] == pair.tokens[0]:
                tokens.append(pair.tokens[1])
            else:
                tokens.append(pair.tokens[0])

        super().__init__(pools, tokens)

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        """Implementation of get_amount_out that uses the fact that all pools are pairs"""
        for pool in self.pools:
            # amount_out of each iteration is amount_in of next one
            amount_in = pool.get_amount_out(amount_in)
        return amount_in

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        """Implementation of get_amount_in that uses the fact that all pools are pairs"""
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
        max_slippage: int = None,
        trade_type: TradeType = None,
    ):
        """Trade involving a sequence of liquidity pools"""
        super().__init__(amount_in, amount_out, route, max_slippage, trade_type)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.route.symbols}: {self._str_in_out})'

    @classmethod
    def best_trade_exact_in(
        cls,
        pools: list[LiquidityPair],
        amount_in: TokenAmount,
        token_out: Token,
        max_hops: int = 1,
        max_slippage: int = None,
    ) -> TradePairs:
        trades = cls.trades_exact_in(
            pools,
            amount_in,
            token_out,
            max_hops,
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
                route = RoutePairs([*current_pools, pool], original_amount_in.token, token_out)
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
        max_slippage: int = None,
    ) -> TradePairs:
        trades = cls.trades_exact_out(
            pools,
            token_in,
            amount_out,
            max_hops,
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
                route = RoutePairs([pool, *current_pools], token_in, original_amount_out.token)
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
                    max_slippage=max_slippage,
                    current_pools=[pool, *current_pools],
                    original_amount_out=original_amount_out,
                    best_trades=best_trades
                )
        return best_trades
