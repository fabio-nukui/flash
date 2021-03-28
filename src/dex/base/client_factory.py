import json
import os
from typing import Type

from web3 import Web3


def load_abi(name: str, script_path: str) -> dict[str, dict]:
    dir_path = os.path.dirname(script_path)
    full_path = os.path.join(dir_path, 'abi', f'{name}.json')
    with open(full_path) as f:
        return json.load(f)


def _load_addresses(name: str, script_path: str) -> dict[str, str]:
    dir_path = os.path.dirname(script_path)
    full_path = os.path.join(dir_path, 'address', f'{name}.json')
    with open(full_path) as f:
        return json.load(f)


class DexClient:
    abis: dict[str, dict]
    addresses: dict[str, str]
    chain_id: int
    swap_fee: int

    def __init__(
        self,
        address: str,
        private_key: str,
        provider: Web3
    ):
        """Client with methods to interact with a decentralized exchange"""
        self.address = Web3.toChecksumAddress(address)
        self.private_key = private_key
        self.provider = provider


class ProtocolFactory:
    def __init__(self, abi_names: list[str], client_cls: DexClient, script_path: str):
        """Factory for dex protocol implementations

        Args:
            abi_names (List[str]): List of filenames with ABIs, without .json suffix
            client_cls (DexClient): Subclass of DexClient that will be returned by factory
            script_path (str): Location of script that instatiated the factory (__file__)
        """
        self.abis = {
            name: load_abi(name, script_path)
            for name in abi_names
        }
        self.client_cls = client_cls
        self._script_path = script_path

    def __call__(
        self,
        class_name: str,
        dex_name: str,
        chain_id: int,
        swap_fee: int,
    ) -> Type[DexClient]:
        """Return a class that represents a dex protocol implementation

        class_name (str): Name of class to be used in repr (e.g.: PancakeswapClient)
        dex_name (str): Name of dex, must have an address .json file (e.g.: uniswap, pancakeswap)
        chain_id (int): ID of blockchain (1 for ethereum mainnet, 56 for BSC)
        swap_fee (int): Base swap fee of exchange in basis points (1/10_000)
        """
        class Client(self.client_cls):
            abis: dict[str, dict]
            addresses: dict
            chain_id: int
            swap_fee: int

            def __init__(
                self,
                address: str,
                private_key: str,
                provider: Web3,
                *args,
                **kwargs
            ):
                super().__init__(address, private_key, provider)

            def __repr__(self):
                return f'{self.__class__.__name__}(address={self.address})'

        Client.abis = self.abis
        Client.addresses = _load_addresses(dex_name, self._script_path)[str(chain_id)]
        Client.chain_id = chain_id
        Client.swap_fee = swap_fee
        Client.__name__ = class_name

        return Client
