from __future__ import annotations

import functools
import json
import logging
from enum import Enum
from typing import Union, overload

from web3 import Web3
from web3.contract import Contract

import configs

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


class Route:
    def __init__(
        self,
        pools: list[LiquidityPool],
        token_in: Token,
        token_out: Token,
        tokens: list[Token] = None,
    ):
        """Route of liquidity pools, use to compute trade with in/out amounts"""
        assert token_in in pools[0].tokens
        assert token_out in pools[-1].tokens
        self.pools = pools
        self.token_in = token_in
        self.token_out = token_out
        self.tokens = tokens or []

    @property
    def symbols(self) -> str:
        return '->'.join(token.symbol for token in self.tokens)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.symbols})'

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        raise NotImplementedError

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        raise NotImplementedError


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
