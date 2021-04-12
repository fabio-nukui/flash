import json
import pathlib
from typing import Union

from web3.contract import Contract
from web3 import Web3

from core import LiquidityPair, Token, TokenAmount, TradePairs


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


class TradePairsMixin:
    """Mixin class for Dex based on liquidity pool pairs."""
    def best_trade_exact_out(
        self,
        token_in: Token,
        amount_out: TokenAmount,
        max_hops: int = 1,
        hop_penalty: float = None,
        max_slippage: int = None,
    ) -> TradePairs:
        return TradePairs.best_trade_exact_out(
            self.pairs,
            token_in,
            amount_out,
            max_hops,
            hop_penalty,
            max_slippage,
        )

    def best_trade_exact_in(
        self,
        amount_in: TokenAmount,
        token_out: Token,
        max_hops: int = 1,
        hop_penalty: float = None,
        max_slippage: int = None,
    ) -> TradePairs:
        return TradePairs.best_trade_exact_in(
            self.pairs,
            amount_in,
            token_out,
            max_hops,
            hop_penalty,
            max_slippage,
        )


class UniV2PairInitMixin:
    """Mixin class for alternative instantiation of liquidity pair using
    uniswapV2 pair contract functions:
        - token0() returns (address token0)
        - token1() returns (address token1)
        - getReserves() returns (uint112 reserve0, uint112 reserve1, uint32 _blockTimestampLast)
    """
    @classmethod
    def from_address(
        cls,
        chain_id: int,
        fee: int,
        address: str = None,
        abi: dict = None,
        web3: Web3 = None,
        contract: Contract = None,
    ) -> LiquidityPair:
        if not issubclass(cls, LiquidityPair):
            raise Exception('UniV2PairInitMixin can only be used in LiquidityPair subclasses')
        if contract is None:
            if address is None or abi is None or web3 is None:
                raise ValueError('`contract` or (`address` + `abi` + `web3`) must be passed')
            contract = web3.eth.contract(address=address, abi=abi)
        if web3 is None:
            web3 = contract.web3

        token_0_address = contract.functions.token0().call()
        token_1_address = contract.functions.token1().call()
        reserve_0, reserve_1, last_timestamp = contract.functions.getReserves().call()

        reserves = (
            TokenAmount(Token(chain_id, token_0_address, web3=web3), reserve_0),
            TokenAmount(Token(chain_id, token_1_address, web3=web3), reserve_1)
        )

        return cls(reserves, fee, contract=contract)
