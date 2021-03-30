from __future__ import annotations

import json
import pathlib

from web3 import Web3


class DexProtocol:
    def __init__(self, script_path: str, abi_filenames: list[str]):
        """Decentralized exchange protocol, which could have more than one
        implementation (e.g.: uniswapV2 / sushiswap / pancakeswap)

        Args:
            script_path (str): Path of script, use __file__
            abi_filenames (list[str]): Name of abi files to load in 'abi' directory
        """
        self.dir_path = pathlib.Path(script_path).parent.absolute()
        self.abis = {
            filename: self._get_abi(filename)
            for filename in abi_filenames
        }

    def _get_abi(self, filename: str) -> dict[str, dict]:
        with open(self.dir_path / 'abi' / filename) as f:
            return json.load(f)


class Dex:
    def __init__(
        self,
        protocol: DexProtocol,
        chain_id: int,
        addresses_filename: str,
        fee: int,
    ):
        """Implementation of a dex protocol in a blockchain

        Args:
            protocol (Protocol): Protocol which this client implements
            chain_id (int): Chain ID of dex (e.g.: 1 for ethereum main net, 56 for BSC)
            addresses_filename (str): Name of file to load 'address' directory
            fee (int): Fee in basis points for swaps (e.g.: 0.3% = 30 basis points)
        """
        self.dir_path = protocol.dir_path
        self.abis = protocol.abis
        self.chain_id = chain_id
        self.addresses = self._get_addresses(addresses_filename)
        self.fee = fee
        self.provider: Web3 = None

    def _get_addresses(self, filename: str) -> dict[str, str]:
        with open(self.dir_path / 'address' / filename) as f:
            return json.load(f)[str(self.chain_id)]

    def connect(self, provider: Web3):
        """Populate data from blockchain using web3 provider, to be implemented by subclasses"""
        raise NotImplementedError


class BaseClient:
    def __init__(
        self,
        dex: Dex,
        caller_address: str,
        private_key: str,
        provider: Web3,
        *args,
        **kwargs,
    ):
        """Client to interact with a decentralized exchange

        Args:
            dex (Dex): Dex to be used implementation
            caller_address (str): Address of caller to trigger contracts
            private_key (str): Prvate key of caller to sign transactions
            provider (Web3): Web3 provider to interact with blockchain
        """
        self.dex = dex
        self.caller_address = Web3.toChecksumAddress(caller_address)
        self.private_key = private_key

        self.dex.connect(provider, *args, **kwargs)
