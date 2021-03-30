from web3 import Web3

from core.entities import Token, TokenAmount
from tools.cache import ttl_cache

LENDING_PRECISION = int(10 ** 18)
PRECISION = int(10 ** 18)
FEE_DENOMINATOR = 10_000  # We use basis points (1/10_000) instead of vyper contract's 1/1e10
N_ITERATIONS = 255  # Number of iterations for numeric calculations


class CurvePool:
    def __init__(
        self,
        name: str,
        tokens: list[Token],
        pool_address: str,
        pool_token_address: str,
        pool_abi: str,
        pool_token_abi: str,
        fee: int,
        provider: Web3
    ):
        self.name = name
        self.tokens = tokens
        self.pool_contract = provider.eth.contract(pool_address, abi=pool_abi)
        self.pool_token_contract = provider.eth.contract(pool_token_address, abi=pool_token_abi)
        self.fee = fee

        self.n_coins = len(self.tokens)
        self._rates = tuple(int(10 ** t.decimals) for t in self.tokens)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name})'

    @property
    def reserves(self) -> list[TokenAmount]:
        return [
            TokenAmount(token, balance)
            for token, balance in zip(self.tokens, self._balance())
        ]

    # Internal functions based from curve's 3pool contract:
    # https://github.com/curvefi/curve-contract/blob/master/contracts/pools/3pool/StableSwap3Pool.vy

    @ttl_cache()
    def _balance(self) -> list[int]:
        return [
            self.pool_contract.functions.balances(i).call()
            for i in range(self.n_coins)
        ]

    @ttl_cache(ttl=120)  # _A should vary slowly over time, cache can have greater TTL
    def _A(self):
        return self.pool_contract.functions.A().call()

    def _xp(self) -> tuple[int, ...]:
        return tuple(
            rate * balance // LENDING_PRECISION
            for rate, balance in zip(self._rates, self._balance())
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
