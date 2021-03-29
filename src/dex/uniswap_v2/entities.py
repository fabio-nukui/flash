from web3 import Web3

from entities import TokenAmount
from tools.cache import ttl_cache


class UniV2Pair:
    def __init__(
        self,
        reserve_0: TokenAmount,
        reserve_1: TokenAmount,
        factory_address: str,
        init_code_hash: str,
        abi: dict,
        provider: Web3
    ):
        self.reserve_0 = reserve_0
        self.reserve_1 = reserve_1
        self.factory_address = factory_address
        self.init_code_hash = init_code_hash
        self.abi = abi
        self.provider = provider

        self.lp_token_address = self._get_lp_token_address()
        self.latest_transaction_timestamp = None

    def _get_lp_token_address(self) -> str:
        """Return address of liquidity pool tokens"""
        token_a, token_b = sorted([self.reserve_0.token, self.reserve_1.token])

        encoded_tokens = Web3.solidityKeccak(
            ['address', 'address'], (token_a.address, token_b.address))

        prefix = Web3.toHex(hexstr='ff')
        raw = Web3.solidityKeccak(
            ['bytes', 'address', 'bytes', 'bytes'],
            [prefix, self.factory_address, encoded_tokens, self.init_code_hash]
        )
        return Web3.toChecksumAddress(raw.hex()[-40:])

    @property
    @ttl_cache
    def reserves(self) -> tuple[TokenAmount, TokenAmount]:
        self.update_amounts()
        return (self.reserve_0, self.reserve_1)

    def update_amounts(self):
        """Update the reserve amounts of both token pools and the unix timestamp of the latest
        transaction"""
        reserve_a, reserve_b = sorted([self.reserve_0, self.reserve_1])
        pair_contract = self.provider.eth.contract(address=self.lp_token_address, abi=self.abi)
        amount_a, amount_b, timestamp = pair_contract.functions.getReserves().call()

        reserve_a.amount = amount_a
        reserve_b.amount = amount_b
        self.latest_transaction_timestamp = timestamp


class UniV2Route:
    def __init__():
        pass
