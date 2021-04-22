from __future__ import annotations

from typing import Callable, Union

from web3 import Web3
from web3.contract import Contract

import configs
from core import LiquidityPair, TokenAmount
from tools.cache import ttl_cache

from ..base import UniV2PairInitMixin

N_PAIRS_CACHE = 50_000  # Must be at least equal to number of pairs in strategy


class UniV2Pair(LiquidityPair, UniV2PairInitMixin):
    def __init__(
        self,
        reserves: tuple[TokenAmount, TokenAmount],
        fee: Union[int, Callable],
        abi: dict = None,
        web3: Web3 = None,
        factory_address: str = None,
        init_code_hash: str = None,
        contract: Contract = None,
    ) -> UniV2Pair:
        if contract is None:
            if abi is None or web3 is None:
                raise ValueError('`contract` or (`abi` + `web3`) must be passed')
            address = self._get_address(
                reserves[0].token.address,
                reserves[1].token.address,
                factory_address,
                init_code_hash
            )
            fee: int = fee(address) if callable(fee) else fee
            contract = web3.eth.contract(address=address, abi=abi)
        super().__init__(reserves, fee, contract=contract)

    @staticmethod
    def _get_address(
        token_0_address: str,
        token_1_address: str,
        factory_address: str,
        init_code_hash: str,
    ) -> str:
        """Return address of liquidity pool using uniswap_v2's implementation of CREATE2"""
        address_0, address_1 = sorted([token_0_address, token_1_address])
        encoded_tokens = Web3.solidityKeccak(
            ['address', 'address'], (address_0, address_1))

        prefix = Web3.toHex(hexstr='ff')
        raw = Web3.solidityKeccak(
            ['bytes', 'address', 'bytes', 'bytes'],
            [prefix, factory_address, encoded_tokens, init_code_hash]
        )
        return Web3.toChecksumAddress(raw.hex()[-40:])

    @ttl_cache(N_PAIRS_CACHE)
    def _get_reserves(self):
        return self.contract.functions.getReserves().call(block_identifier=configs.BLOCK)
