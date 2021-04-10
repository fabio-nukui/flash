from web3 import Web3

from core import TokenAmount, LiquidityPair
from tools.cache import ttl_cache

N_PAIRS_CACHE = 1000  # Must be at least equal to number of pairs in strategy


class ValueDefiPair(LiquidityPair):
    def __init__(
        self,
        reserves: tuple[TokenAmount, TokenAmount],
        abi: dict,
        fee: int,
        web3: Web3,
        address: str,
        token_0_weight: int,
    ):
        super().__init__(reserves, abi, fee, web3)

        self.address = address
        self.weights = (token_0_weight, 100 - token_0_weight)
        self.contract = self.web3.eth.contract(address=self.address, abi=self.abi)
        self.latest_transaction_timestamp = None

        if self._reserve_0.is_empty() or self._reserve_1.is_empty():
            self._update_amounts()

    @ttl_cache(N_PAIRS_CACHE)
    def _get_reserves(self):
        return self.contract.functions.getReserves().call()

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

        return reserve_out * (1 - base ** power)

    def get_amount_in(self, amount_out: TokenAmount) -> TokenAmount:
        if self.weights == (50, 50):
            return super().get_amount_in(amount_out)
        reserve_in, reserve_out = self._get_in_out_reserves(amount_out=amount_out)
        weight_in, weight_out = self._get_in_out_weights(amount_out=amount_out)

        fee_impact = 10_000 / (10_000 - self.fee)
        base = reserve_out.amount / (reserve_out.amount - amount_out.amount)
        power = weight_out / weight_in

        return reserve_in * ((base ** power - 1) * fee_impact) + 1
