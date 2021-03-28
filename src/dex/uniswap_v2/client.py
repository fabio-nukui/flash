from web3 import Web3

from ..base.client_factory import ProtocolFactory, DexClient


MAX_UINT256 = 2 ** 256 - 1

FACTORY_ABI = 'IUniswapV2Factory'
ROUTER_ABI = 'IUniswapV2Router'
PAIR_ABI = 'IUniswapV2Pair'


class UniswapV2Client(DexClient):
    def __init__(self, address: str, private_key: str, provider: Web3):
        super().__init__(address, private_key, provider)

        self.factory_contract = self.provider.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['factory']),
            abi=self.abis[FACTORY_ABI]
        )
        self.router = self.provider.eth.contract(
            address=Web3.toChecksumAddress(self.addresses['router']),
            abi=self.abis[ROUTER_ABI]
        )

    def get_amount_out(self, amount_in: int, reserve_in: int, reserve_out: int) -> int:
        """
        Given an input asset amount, returns the maximum output amount of the
        other asset (accounting for fees) given reserves.

        :param amount_in: Amount of input asset.
        :param reserve_in: Reserve of input asset in the pair contract.
        :param reserve_out: Reserve of input asset in the pair contract.
        :return: Maximum amount of output asset.
        """
        assert amount_in > 0 and reserve_in > 0 and reserve_out > 0
        amount_in_with_fee = amount_in * (10_000 - self.swap_fee)
        numerator = amount_in_with_fee * reserve_out
        denominator = reserve_in * 10_000 + amount_in_with_fee

        return numerator // denominator

    def get_amount_in(self, amount_out: int, reserve_in: int, reserve_out: int) -> int:
        """
        Returns the minimum input asset amount required to buy the given
        output asset amount (accounting for fees) given reserves.

        :param amount_out: Amount of output asset.
        :param reserve_in: Reserve of input asset in the pair contract.
        :param reserve_out: Reserve of input asset in the pair contract.
        :return: Required amount of input asset.
        """
        assert amount_out > 0 and reserve_in > 0 and reserve_out > 0
        assert amount_out < reserve_out, 'Insufficient liquidity'
        numerator = reserve_in * amount_out * 10_000
        denominator = (reserve_out - amount_out) * (10_000 - self.swap_fee)

        return numerator // denominator + 1


UniswapV2Protocol = ProtocolFactory([FACTORY_ABI, ROUTER_ABI, PAIR_ABI], UniswapV2Client, __file__)
