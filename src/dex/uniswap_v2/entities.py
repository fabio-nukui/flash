from __future__ import annotations

from web3 import Web3

from core import LiquidityPair, TokenAmount
from tools.cache import ttl_cache

N_PAIRS_CACHE = 1000  # Must be at least equal to number of pairs in strategy


class UniV2Pair(LiquidityPair):
    def __init__(
        self,
        reserves: tuple[TokenAmount, TokenAmount],
        abi: dict,
        fee: int,
        web3: Web3,
        factory_address: str,
        init_code_hash: str,
    ):
        super().__init__(reserves, abi, fee, web3)

        self.address = self._get_address(factory_address, init_code_hash)
        self.contract = self.web3.eth.contract(address=self.address, abi=self.abi)
        self.latest_transaction_timestamp: int = None

        if self._reserve_0.is_empty() or self._reserve_1.is_empty():
            self._update_amounts()

    def _get_address(self, factory_address: str, init_code_hash: str) -> str:
        """Return address of pair's liquidity pool"""
        encoded_tokens = Web3.solidityKeccak(
            ['address', 'address'], (self._reserve_0.token.address, self._reserve_1.token.address))

        prefix = Web3.toHex(hexstr='ff')
        raw = Web3.solidityKeccak(
            ['bytes', 'address', 'bytes', 'bytes'],
            [prefix, factory_address, encoded_tokens, init_code_hash]
        )
        return Web3.toChecksumAddress(raw.hex()[-40:])

    @ttl_cache(N_PAIRS_CACHE)
    def _get_reserves(self):
        return self.contract.functions.getReserves().call()
