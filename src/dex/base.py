import json
import pathlib
from typing import Union

from web3 import Web3


class DexProtocol:
    def __init__(
        self,
        abi_filepaths: list[Union[str, pathlib.Path]],
        chain_id: int,
        addresses_filepath: str,
        web3: Web3,
        fee: int = None,
        **kwargs
    ):
        """Decentralized exchange protocol

        Args:
            abi_filepaths (list[Union[str, pathlib.Path]]): Paths with abi .json files
            chain_id (int): Chain ID of protocol implementation (e.g.: 56 for Binance Smart Chain)
            addresses_filepath (str): pathlib.Path to relevant addresses .json file
            web3 (Web3): Web3 provider to interact with blockchain
            fee (int): Swap fee in basis points (e.g.: 20 for pancakeswap's 0.2% fee)
        """
        self.abis = {
            filepath: self._get_abi(filepath)
            for filepath in abi_filepaths
        }
        self.chain_id = chain_id
        self.addresses = self._get_addresses(addresses_filepath, chain_id)
        self.fee = fee
        self.web3 = web3
        self._connect(**kwargs)

    def __repr__(self):
        return f'{self.__class__.__name__}'

    @staticmethod
    def _get_abi(filepath: Union[str, pathlib.Path]) -> dict[str, dict]:
        with open(filepath) as f:
            return json.load(f)

    @staticmethod
    def _get_addresses(filepath: Union[str, pathlib.Path], chain_id: int) -> dict:
        with open(filepath) as f:
            return json.load(f)[str(chain_id)]

    def _connect(self, **kwargs):
        """To be implemented by subclasses, uses web3 to connect to blockchain."""
        raise NotImplementedError
