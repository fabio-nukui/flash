from __future__ import annotations

import json
import pathlib
from typing import overload

from web3 import Web3

MAX_UINT_256 = 2 ** 256 - 1

ERC20_ABI_FILE = pathlib.Path(__file__).parent / 'abi' / 'IERC20.json'
ERC20_ABI = json.load(open(ERC20_ABI_FILE))
EMPTY_AMOUNT = -42


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

        if web3 is None:
            self.contract = None
            assert decimals is not None, f'No decimals provided for token id={address}'
        else:
            self.contract = web3.eth.contract(address=self.address, abi=self.abi)
            if symbol is None:
                self.symbol = self.contract.functions.symbol().call()
            if decimals is None:
                self.decimals = self.contract.functions.decimals().call()

    def __repr__(self):
        return f'{self.__class__.__name__}(symbol={self.symbol}, address={self.address})'

    def __eq__(self, other):
        return (
            self.address == other.address
            and self.chain_id == other.chain_id
        )

    def __hash__(self):
        return int(self.address, 16) + self.chain_id

    def __lt__(self, other):
        """Use same logic as Uniswap:
            https://github.com/Uniswap/uniswap-sdk-core/blob/main/src/entities/token.ts#L37"""
        assert self.chain_id == other.chain_id, \
            f'Cannot compare tokens in different chains {self.chain_id} / {other.chain_id}'
        return self.address.lower() < other.address.lower()


class TokenAmount:
    def __init__(self, token: Token, amount: int = EMPTY_AMOUNT):
        if amount != EMPTY_AMOUNT:
            assert 0 <= amount < MAX_UINT_256, f'{amount=} is out of bounds'
        self.token = token
        self.amount = amount

    def __repr__(self) -> str:
        if self.amount == EMPTY_AMOUNT:
            return f'{self.__class__.__name__}({self.token.symbol}: None)'
        amount_str = f'{self.amount / 10 ** self.token.decimals:,.2f}'  # type: ignore
        return f'{self.__class__.__name__}({self.token.symbol}: {amount_str})'

    def is_empty(self):
        return self.amount == EMPTY_AMOUNT

    def __lt__(self, other):
        if type(self) is not type(other) or self.token != other.token:
            raise TypeError("'<' only suported fot TokenAmounts of same token")
        return self.token < other.token

    def __eq__(self, other):
        return (
            type(self) is type(other)
            and self.token == other.token
            and self.amount == other.amount
        )

    def __mul__(self, other) -> TokenAmount:
        if not isinstance(other, int):
            raise TypeError('TokenAmount can only multiply with int')
        return TokenAmount(self.token, self.amount * other)

    def __floordiv__(self, other) -> TokenAmount:
        if not isinstance(other, int):
            raise TypeError('TokenAmount can only floor divide with int')
        return TokenAmount(self.token, self.amount // other)

    def __truediv__(self, other) -> Price:
        if type(self) is not type(other):
            raise TypeError('TokenAmount can only divide another TokenAmount')
        return Price(self, other)


class Price:
    def __init__(self, amount_in: TokenAmount, amount_out: TokenAmount):
        self.amount_in = amount_in
        self.amount_out = amount_out
        self.value = self.amount_in.amount // self.amount_out.amount

    def __repr__(self):
        return f'{self.__class__.__name__}({self.amount_in}/{self.amount_out}: {self.value:,})'

    @overload
    def __mul__(self, other: int) -> Price: ...  # noqa: E704

    @overload
    def __mul__(self, other: TokenAmount) -> TokenAmount: ...  # noqa: E704

    def __mul__(self, other):
        if isinstance(other, int):
            return Price(self.amount_in * other, self.amount_out)
        if isinstance(other, TokenAmount):
            if self.amount_out.token != other.token:
                raise TypeError(
                    "Can only multiply Price whose amount_out Token is same as ValueTokens' Token"
                )
            return self.amount_in * other.amount
