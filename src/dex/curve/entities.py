from __future__ import annotations

from typing import Iterable

from web3 import Web3
from web3.exceptions import BadFunctionCallOutput

import configs
from core import LiquidityPool, Token, TokenAmount, Trade
from core.base import TradeType
from tools.cache import ttl_cache

LENDING_PRECISION = 10 ** 18
PRECISION = 10 ** 18
FEE_DENOMINATOR = 10_000  # We use basis points (1/10_000) instead of vyper contract's 1/1e10
N_ITERATIONS = 255  # Number of iterations for numeric calculations

N_POOLS_CACHE = 100  # Must be at least equal to number of pools in strategy


class CurvePool(LiquidityPool):
    def __init__(
        self,
        name: str,
        chain_id: int,
        web3: Web3,
        pool_address: str,
        pool_token_address: str,
        pool_abi: str,
        pool_token_abi: str,
        fee: int,
    ):
        self.name = name
        self.chain_id = chain_id
        self.web3 = web3
        self.pool_token_contract = web3.eth.contract(pool_token_address, abi=pool_token_abi)
        super().__init__(
            fee,
            reserves=(TokenAmount(token) for token in self.get_tokens()),
            contract=web3.eth.contract(pool_address, abi=pool_abi)
        )

        self.n_coins = len(self.tokens)
        self._rates = tuple(10 ** t.decimals for t in self.tokens)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name})'

    @property
    def balances(self) -> list[int]:
        return [reserve.amount for reserve in self.reserves]

    def get_tokens(self) -> list[Token]:
        i = 0
        tokens = []
        while True:
            try:
                token_address = \
                    self.contract.functions.coins(i).call(block_identifier=configs.BLOCK)
            except BadFunctionCallOutput:
                return tokens
            tokens.append(Token(self.chain_id, token_address, web3=self.web3))
            i += 1

    def get_amount_out(self, amount_in: TokenAmount, token_out: Token) -> TokenAmount:
        amount_out = self._get_dy(
            self.tokens.index(amount_in.token),
            self.tokens.index(token_out),
            amount_in.amount
        )
        return TokenAmount(token_out, amount_out)

    # Internal functions based from curve's 3pool contract:
    # https://github.com/curvefi/curve-contract/blob/master/contracts/pools/3pool/StableSwap3Pool.vy

    def _update_balance(self) -> list[int]:
        for reserve, bal in zip(self._reserves, self._get_balance()):
            reserve.amount = bal

    @ttl_cache(N_POOLS_CACHE)
    def _get_balance(self) -> list[int]:
        return [
            self.contract.functions.balances(i).call(block_identifier=configs.BLOCK)
            for i in range(self.n_coins)
        ]

    @ttl_cache(ttl=180)  # _A should vary slowly over time, cache can have greater TTL
    def _A(self):
        return self.contract.functions.A().call(block_identifier=configs.BLOCK)

    def _xp(self) -> tuple[int, ...]:
        return tuple(
            rate * balance // LENDING_PRECISION
            for rate, balance in zip(self._rates, self.balances)
        )

    def _get_D(self, xp: tuple[int, ...], amp: int) -> int:
        S = 0
        for _x in xp:
            S += _x
        if S == 0:
            return 0

        Dprev = 0
        D = S
        Ann = amp * self.n_coins
        for _i in range(N_ITERATIONS):
            D_P = D
            for _x in xp:
                # If division by 0, this will be borked: only withdrawal will work. And that is good
                D_P = D_P * D // (_x * self.n_coins)
            Dprev = D
            D = (Ann * S + D_P * self.n_coins) * D // ((Ann - 1) * D + (self.n_coins + 1) * D_P)
            if abs(D - Dprev) <= 1:
                break
        return D

    def _get_y(self, i: int, j: int, x: int, xp_: tuple[int, ...], amp: int) -> int:
        # x in the input is converted to the same price/precision

        assert i != j             # dev: same coin
        assert j >= 0             # dev: j below zero
        assert j < self.n_coins   # dev: j above N_COINS

        # should be unreachable, but good for safety
        assert i >= 0
        assert i < self.n_coins

        D = self._get_D(xp_, amp)
        c = D
        S_ = 0
        Ann = amp * self.n_coins

        _x = 0
        for _i in range(self.n_coins):
            if _i == i:
                _x = x
            elif _i != j:
                _x = xp_[_i]
            else:
                continue
            S_ += _x
            c = c * D // (_x * self.n_coins)
        c = c * D // (Ann * self.n_coins)
        b = S_ + D // Ann  # - D
        y_prev = 0
        y = D
        for _i in range(N_ITERATIONS):
            y_prev = y
            y = (y * y + c) // (2 * y + b - D)
            if abs(y - y_prev) <= 1:
                break
        return y

    def _get_dy(self, i: int, j: int, dx: int) -> int:
        dx = int(dx)
        # Fetch all data from blockchain in beggining of call
        _xp = self._xp()
        amp = self._A()

        x = _xp[i] + (dx * self._rates[i] // PRECISION)
        y = self._get_y(i, j, x, _xp, amp)
        dy = (_xp[j] - y - 1) * PRECISION // self._rates[j]
        fee = self.fee * dy // FEE_DENOMINATOR
        return dy - fee


class CurveTrade(Trade):
    def __init__(
        self,
        pool: CurvePool,
        amount_in: TokenAmount = None,
        amount_out: TokenAmount = None,
        max_slippage: int = None,
    ):
        self.pool = pool
        super().__init__(amount_in, amount_out, max_slippage, trade_type=TradeType.exact_in)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.pool}: {self._str_in_out})'

    def _get_amount_out(self) -> TokenAmount:
        return self.pool.get_amount_out(self.amount_in, self.token_out)

    def _get_amount_in(self) -> TokenAmount:
        raise NotImplementedError("'Exact Out' trades not implemented for curve pools")

    @staticmethod
    def best_trade_exact_in(
        pools: Iterable[CurvePool],
        amoun_in: Token,
        token_out: TokenAmount,
        max_slippage: int = None,
    ) -> CurveTrade:
        best_trades = []
        for pool in pools:
            if amoun_in.token not in pool.tokens or token_out not in pool.tokens:
                continue
            trade = CurveTrade(pool, amoun_in, TokenAmount(token_out), max_slippage=max_slippage)
            best_trades.append(trade)
        return max(best_trades, key=lambda x: x.amount_out)
