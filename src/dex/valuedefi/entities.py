from __future__ import annotations

from web3.contract import Contract
from web3 import Web3

from core import LiquidityPair, TokenAmount
from tools.cache import ttl_cache

import configs
from ..base import UniV2PairInitMixin


N_POOLS_CACHE = 1_000  # Must be at least equal to number of pools in strategy


class ValueDefiPair(LiquidityPair, UniV2PairInitMixin):
    def __init__(
        self,
        reserves: tuple[TokenAmount, TokenAmount],
        fee: int,
        weights: tuple[int, int] = None,
        address: str = None,
        abi: dict = None,
        web3: Web3 = None,
        contract: Contract = None,
    ):
        if contract is None:
            if address is None or abi is None or web3 is None:
                raise ValueError('`contract` or (`address` + `abi` + `web3`) must be passed')
            contract = web3.eth.contract(address, abi=abi)
        if weights is None:
            weights = tuple(
                contract.functions.getTokenWeights().call(block_identifier=configs.BLOCK)
            )
        assert sum(weights) == 100, f'sum(weights) must be 100, received {weights=}'
        self.weights = weights
        super().__init__(reserves, fee, contract=contract)

    def __repr__(self):
        return (
            f'{self.__class__.__name__}'
            f'({self._reserve_0.symbol}/{self._reserve_1.symbol}: '
            f'{self.weights[0]}/{self.weights[1]})'
        )

    @classmethod
    def from_address(cls, chain_id: int, address: str, abi: dict, web3: Web3):
        contract = web3.eth.contract(address, abi=abi)
        fee = contract.functions.getSwapFee().call(block_identifier=configs.BLOCK) * 10

        return super().from_address(chain_id, fee, contract=contract)

    @ttl_cache(N_POOLS_CACHE)
    def _get_reserves(self):
        return self.contract.functions.getReserves().call(block_identifier=configs.BLOCK)

    def _get_in_out_weights(
        self,
        amount_in: TokenAmount = None,
        amount_out: TokenAmount = None
    ) -> tuple[TokenAmount, TokenAmount]:
        if amount_in is None:
            token_in = self.tokens[0] if amount_out.token == self.tokens[1] else self.tokens[1]
        else:
            token_in = amount_in.token
        if token_in == self.tokens[0]:
            weight_in, weight_out = self.weights
        else:
            weight_out, weight_in = self.weights
        return weight_in, weight_out

    def get_amount_out(self, amount_in: TokenAmount) -> TokenAmount:
        if self.weights == (50, 50):
            return super().get_amount_out(amount_in)
        reserve_in, reserve_out = self._get_in_out_reserves(amount_in=amount_in)
        weight_in, weight_out = self._get_in_out_weights(amount_in=amount_in)

        amount_in_with_fee = amount_in.amount * (10_000 - self.fee)
        base = reserve_in.amount * 10_000 / (amount_in_with_fee + reserve_in.amount * 10_000)
        power = weight_in / weight_out

        # Use abs(base) to allow for negative values during optimization tests
        return reserve_out * (1 - abs(base) ** power)

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        if self.weights == (50, 50):
            return super().get_amount_in(amount_out)
        reserve_in, reserve_out = self._get_in_out_reserves(amount_out=amount_out)
        weight_in, weight_out = self._get_in_out_weights(amount_out=amount_out)

        fee_impact = 10_000 / (10_000 - self.fee)
        base = reserve_out.amount / (reserve_out.amount - amount_out.amount)
        power = weight_out / weight_in

        # Use abs(base) to allow for negative values during optimization tests
        return reserve_in * ((abs(base) ** power - 1) * fee_impact) + 1
