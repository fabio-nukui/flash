import json
import pathlib

from web3 import Web3

MAX_UINT_256 = 2 ** 256 - 1

ERC20_ABI_FILE = pathlib.Path(__file__).parent / 'abi' / 'IERC20.json'
ERC20_ABI = json.load(open(ERC20_ABI_FILE))
EMPTY_AMOUNT = -42


class Token:
    def __init__(
        self,
        chain_id: int,
        address: str,
        symbol: str = None,
        decimals: int = None,
        abi: dict = ERC20_ABI,
        provider: Web3 = None,
    ):
        self.chain_id = int(chain_id)
        self.address = Web3.toChecksumAddress(address)
        self.decimals = int(decimals) if decimals is not None else None
        self.symbol = symbol
        self.abi = abi

        if provider is None:
            self.contract = None
            assert decimals is not None, f'No decimals provided for token id={address}'
        else:
            self.contract = provider.eth.contract(address=self.address, abi=self.abi)
            if symbol is None:
                self.symbol = self.contract.functions.symbol().call()
            if decimals is None:
                self.decimals = self.contract.functions.decimals().call()

    def __repr__(self):
        return f'{self.__class__.__name__}(symbol={self.symbol}, address={self.address})'

    def __eq__(self, other):
        return (
            self.address == other.address
            and self.chain_id == other.chain_id
        )

    def __hash__(self):
        return int(self.address, 16) + self.chain_id

    def __lt__(self, other):
        """Use same logic as Uniswap:
            https://github.com/Uniswap/uniswap-sdk-core/blob/main/src/entities/token.ts#L37"""
        assert self.chain_id == other.chain_id, \
            f'Cannot compare tokens in different chains {self.chain_id} / {other.chain_id}'
        return self.address.lower() < other.address.lower()


class TokenAmount:
    def __init__(self, token: Token, amount: int = None):
        if amount is not None:
            assert 0 <= amount < MAX_UINT_256, f'{amount=} is out of bounds'
        self.token = token
        self.amount = amount if amount is not None else EMPTY_AMOUNT

    def __repr__(self) -> str:
        amount_str = f'{self.amount:,}' if self.is_empty else 'None'
        return f'{self.__class__.__name__}({self.token.symbol}: {amount_str}'

    @property
    def is_empty(self):
        return self.amount == EMPTY_AMOUNT

    def __lt__(self, other):
        """Keep same ordering as underlying tokens"""
        return self.token < other.token
