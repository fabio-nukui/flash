from __future__ import annotations

import functools
import json
import logging
from copy import copy
from enum import Enum
from typing import Union, overload

from web3 import Web3
from web3.contract import Contract

import configs
from exceptions import InsufficientLiquidity

log = logging.getLogger(__name__)

MAX_UINT_256 = 2 ** 256 - 1

ERC20_ABI_FILE = 'abis/IERC20.json'
ERC20_ABI = json.load(open(ERC20_ABI_FILE))

DEFAULT_MAX_SLIPPAGE = 30  # Default maximum slippage for trades in basis points


class TradeType(Enum):
    exact_in = 'Exact In'
    exact_out = 'Exact Oout'
    exact = 'Exact In/Out'


class Token:
    def __init__(
        self,
        chain_id: int,
        address: str,
        symbol: str = None,
        decimals: int = None,
        abi: dict = ERC20_ABI,
        web3: Web3 = None,
    ):
        self.chain_id = int(chain_id)
        self.address = Web3.toChecksumAddress(address)
        self.decimals = int(decimals) if decimals is not None else None
        self.symbol = symbol
        self.abi = abi
        self.contract: Contract = None

        if web3 is None:
            assert decimals is not None, f'No decimals provided for token id={address}'
        else:
            self.contract = web3.eth.contract(address=self.address, abi=self.abi)
            if symbol is None:
                self.symbol = self.contract.functions.symbol().call(block_identifier=configs.BLOCK)
            if decimals is None:
                self.decimals = \
                    self.contract.functions.decimals().call(block_identifier=configs.BLOCK)

    def __repr__(self):
        return f'{self.__class__.__name__}(symbol={self.symbol}, address={self.address})'

    def __eq__(self, other):
        if isinstance(other, Token):
            return (
                self.address == other.address
                and self.chain_id == other.chain_id
            )
        return NotImplemented

    def __hash__(self):
        return int(self.address, 16) + self.chain_id

    def __lt__(self, other):
        """Use same logic as Uniswap:
            https://github.com/Uniswap/uniswap-sdk-core/blob/main/src/entities/token.ts#L37"""
        if isinstance(other, Token):
            assert self.chain_id == other.chain_id, \
                f'Cannot compare tokens in different chains {self.chain_id} / {other.chain_id}'
            return self.address.lower() < other.address.lower()
        return NotImplemented


def _not_empty(func):
    """Decorator that checks that TokenAmounts are not empty"""
    @functools.wraps(func)
    def wrapper(*args):
        for arg in args:
            if isinstance(arg, TokenAmount) and arg.is_empty():
                raise ValueError('Operation not supported for empty TokenAmount')
        return func(*args)
    return wrapper


def _same_token(func):
    """Decorator that checks that operatins between TokenAmounts only work if their
        underlying Token is the same"""
    @functools.wraps(func)
    def wrapper(self, other):
        if isinstance(other, TokenAmount):
            if self.token != other.token:
                raise TypeError("Operation only suported for TokenAmounts of same token")
        return func(self, other)
    return wrapper


@functools.total_ordering
class TokenAmount:
    def __init__(self, token: Token, amount: Union[int, float] = None):
        if amount is not None:
            assert -MAX_UINT_256 < amount < MAX_UINT_256, f'{amount=} is out of bounds'
        self.token = token
        self.amount = int(amount) if amount is not None else amount

        self.symbol = self.token.symbol

    def __repr__(self) -> str:
        if self.is_empty():
            return f'{self.__class__.__name__}({self.symbol}: None)'
        if self.amount_in_units > 1:
            return f'{self.__class__.__name__}({self.symbol}: {self.amount_in_units:,.2f})'
        return f'{self.__class__.__name__}({self.symbol}: {self.amount_in_units})'

    def __hash__(self):
        amount = -MAX_UINT_256 if self.is_empty() else self.amount
        return int(self.token.address, 16) + self.token.chain_id + amount

    @property
    def amount_in_units(self) -> float:
        return self.amount / 10 ** self.token.decimals

    def is_empty(self):
        return self.amount is None

    @_not_empty
    def __abs__(self):
        return TokenAmount(self.token, abs(self.amount))

    @_same_token
    @_not_empty
    def __lt__(self, other: Union[TokenAmount, int, float]) -> bool:
        if isinstance(other, (int, float)):
            return self.amount < other
        elif isinstance(other, TokenAmount):
            return self.amount < other.amount
        return NotImplemented

    @_same_token
    @_not_empty
    def __eq__(self, other: Union[TokenAmount, int, float]) -> bool:
        if isinstance(other, (int, float)):
            return self.amount == other
        elif isinstance(other, TokenAmount):
            return self.amount == other.amount
        return NotImplemented

    @_same_token
    @_not_empty
    def __add__(self, other: Union[TokenAmount, int, float]) -> TokenAmount:
        if isinstance(other, (int, float)):
            return TokenAmount(self.token, int(self.amount + other))
        if isinstance(other, TokenAmount):
            return TokenAmount(self.token, self.amount + other.amount)
        return NotImplemented

    @_same_token
    @_not_empty
    def __sub__(self, other: Union[TokenAmount, int, float]) -> TokenAmount:
        if isinstance(other, (int, float)):
            return TokenAmount(self.token, int(self.amount - other))
        if isinstance(other, TokenAmount):
            return TokenAmount(self.token, self.amount - other.amount)
        return NotImplemented

    @_not_empty
    def __mul__(self, other: Union[int, float]) -> TokenAmount:
        if isinstance(other, (int, float)):
            return TokenAmount(self.token, int(self.amount * other))
        return NotImplemented

    @_same_token
    @_not_empty
    def __truediv__(self, other: TokenAmount) -> Price:
        if isinstance(other, TokenAmount):
            return Price(self, other)
        return NotImplemented

    @_not_empty
    def __floordiv__(self, other: Union[int, float]) -> TokenAmount:
        if isinstance(other, (int, float)):
            return TokenAmount(self.token, int(self.amount // other))
        return NotImplemented


class Price:
    def __init__(self, amount_in: TokenAmount, amount_out: TokenAmount):
        self.amount_in = amount_in
        self.amount_out = amount_out
        self.value = self.amount_in.amount / self.amount_out.amount

    def __repr__(self):
        return f'{self.__class__.__name__}({self.amount_in}/{self.amount_out}: {self.value:,})'

    @overload
    def __mul__(self, other: (int, float)) -> Price: ...  # noqa: E704

    @overload
    def __mul__(self, other: TokenAmount) -> TokenAmount: ...  # noqa: E704

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Price(self.amount_in * other, self.amount_out)
        if isinstance(other, TokenAmount):
            if self.amount_out.token != other.token:
                raise TypeError(
                    "Can only multiply Price whose amount_out Token is same as ValueTokens' Token"
                )
            return self.amount_in * other.amount / self.amount_out.amount
        return NotImplemented


class LiquidityPool:
    def __init__(self, fee: int, tokens: Union[list[Token], tuple[Token]], contract: Contract):
        self.fee = fee
        self.contract = contract
        self.address = contract.address
        self.tokens = tokens


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


class RoutePairs:
    def __init__(
        self,
        pools: list[LiquidityPair],
        token_in: Token,
        token_out: Token,
        hop_penalty: float = None,
    ):
        """Route of liquidity pairs, use to compute trade with in/out amounts"""
        assert token_in in pools[0].tokens
        assert token_out in pools[-1].tokens
        self.pools = pools
        self.token_in = token_in
        self.token_out = token_out
        self.hop_penalty = hop_penalty
        self.tokens = self._get_tokens()

    def _get_tokens(self) -> list[Token]:
        tokens = [self.token_in]
        for pair in self.pools:
            if tokens[-1] == pair.tokens[0]:
                tokens.append(pair.tokens[1])
            else:
                tokens.append(pair.tokens[0])
        return tokens

    @property
    def symbols(self) -> str:
        return '->'.join(token.symbol for token in self.tokens)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.symbols})'

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        for i, pair in enumerate(self.pools):
            # amount_out of each iteration is amount_in of next one
            amount_in = pair.get_amount_out(amount_in)
            if i > 0 and self.hop_penalty:
                amount_in //= (1 + self.hop_penalty)
        return amount_in

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        for i, pair in enumerate(reversed(self.pools)):
            # amount_in of each iteration is amount_out of next one
            amount_out = pair.get_amount_in(amount_out)
            if i > 0 and self.hop_penalty:
                amount_out *= (1 + self.hop_penalty)
        return amount_out


class Trade:
    def __init__(
        self,
        amount_in: TokenAmount,
        amount_out: TokenAmount,
        max_slippage: int = None
    ):
        """Decentralized exchange trade:
            - For Exact In trade, set amount_in.amount to zero
            - For Exact Out trade, set amount_out.amount to zero
            - For Exact In/Out trade, set both amounts to non-zero
        """
        assert not amount_in.is_empty() or not amount_out.is_empty(), \
            'At least one of amount_in or amount_out must be not empty'

        self.token_in = amount_in.token
        self.token_out = amount_out.token
        self.max_slippage = DEFAULT_MAX_SLIPPAGE if max_slippage is None else max_slippage

        if not amount_in.is_empty() and amount_out.is_empty():
            self.trade_type = TradeType.exact_in
            self.amount_in = amount_in
            self.max_amount_in = amount_in
            self.amount_out = self._get_amount_out()
            self.min_amount_out = self.amount_out * 10_000 // (10_000 + self.max_slippage)
        elif amount_in.is_empty() and not amount_out.is_empty():
            self.trade_type = TradeType.exact_out
            self.amount_out = amount_out
            self.min_amount_out = amount_out
            self.amount_in = self._get_amount_in()
            self.max_amount_in = self.amount_in * (10_000 + self.max_slippage) // 10_000
        else:
            self.trade_type = TradeType.exact
            self.amount_in = amount_in
            self.max_amount_in = amount_in
            self.amount_out = amount_out
            self.min_amount_out = amount_out

    def __repr__(self):
        return f'{self.__class__.__name__}({self._str_in_out})'

    @property
    def _str_in_out(self) -> str:
        if self.trade_type == TradeType.exact_in:
            return f'Exact In={self.amount_in}; Est. Out={self.amount_out}'
        elif self.trade_type == TradeType.exact_out:
            return f'Est. In={self.amount_in}; Exact Out={self.amount_out}'
        return f'Exact In={self.amount_in}; Exact Out={self.amount_out}'

    def _get_amount_in(self) -> TokenAmount:
        raise NotImplementedError

    def _get_amount_out(self) -> TokenAmount:
        raise NotImplementedError


class TradePairs(Trade):
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

    def _get_amount_in(self) -> TokenAmount:
        return self.route.get_amount_in(self.amount_out)

    def _get_amount_out(self) -> TokenAmount:
        return self.route.get_amount_out(self.amount_in)

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
                    current_pools=[pool, *current_pools],
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
