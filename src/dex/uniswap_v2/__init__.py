import json
from typing import Union

from web3 import Web3

import configs
import tools
from core import Token

from .entities import UniV2Pair
from .uniswap_v2_protocol import UniswapV2Protocol


class PancakeswapDex(UniswapV2Protocol):
    def __init__(
        self,
        tokens: list[Union[dict, Token]] = None,
        pools_addresses: list[str] = None,
        web3: Web3 = None,
        verbose_init: bool = False,
        addresses_filepath: str = 'addresses/dex/uniswap_v2/pancakeswap.json',
        fee: int = 20,
    ):
        web3 = tools.w3.get_web3() if web3 is None else web3
        if pools_addresses is None:
            if tokens is None:
                with open('addresses/dex/uniswap_v2/pancakeswap_default_tokens.json') as f:
                    tokens_data = json.load(f)
                tokens = [Token(**data) for data in tokens_data]
            elif isinstance(tokens[0], dict):
                tokens = [Token(**data, web3=web3) for data in tokens]
            elif not isinstance(tokens[0], Token):
                raise ValueError(f"'tokens' must be a list of dict or Token, received {tokens}")

        super().__init__(
            chain_id=56,
            addresses_filepath=addresses_filepath,
            fee=fee,
            web3=web3,
            tokens=tokens,
            pools_addresses=pools_addresses,
            verbose_init=verbose_init,
        )


class PancakeswapDexV2(PancakeswapDex):
    def __init__(
        self,
        tokens: list[Union[dict, Token]] = None,
        pools_addresses: list[str] = None,
        web3: Web3 = None,
        verbose_init: bool = False,
        addresses_filepath: str = 'addresses/dex/uniswap_v2/pancakeswap_v2.json',
        fee: int = 25,
    ):
        super().__init__(tokens, pools_addresses, web3, verbose_init, addresses_filepath, fee)


class MDex(UniswapV2Protocol):
    def __init__(
        self,
        tokens: list[Union[dict, Token]] = None,
        pools_addresses: list[str] = None,
        web3: Web3 = None,
        verbose_init: bool = False,
    ):
        web3 = tools.w3.get_web3() if web3 is None else web3
        addresses_filepath = 'addresses/dex/uniswap_v2/mdex.json'
        if pools_addresses is None:
            if tokens is None:
                with open('addresses/dex/uniswap_v2/mdex_default_tokens.json') as f:
                    tokens_data = json.load(f)
                tokens = [Token(**data) for data in tokens_data]
            elif isinstance(tokens[0], dict):
                tokens = [Token(**data, web3=web3) for data in tokens]
            elif not isinstance(tokens[0], Token):
                raise ValueError(f"'tokens' must be a list of dict or Token, received {tokens}")

        super().__init__(
            chain_id=56,
            addresses_filepath=addresses_filepath,
            web3=web3,
            fee=self._get_fee,
            tokens=tokens,
            pools_addresses=pools_addresses,
            verbose_init=verbose_init,
        )

    def _get_fee(self, pair_address: str) -> int:
        func = self.factory_contract.functions.getPairFees
        return func(pair_address).call(block_identifier=configs.BLOCK)


__all__ = [
    'MDex',
    'PancakeswapDex',
    'PancakeswapDexV2',
    'UniV2Pair',
]
