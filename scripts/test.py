import json
import logging
import pathlib
from typing import Type, Union

from web3.contract import Contract

import configs
import startup
import tools
from arbitrage import PairManager
from core import Token, TokenAmount
from dex import DexProtocol

log = logging.getLogger(__name__)

startup.setup()
web3 = tools.w3.get_web3()
account = web3.eth.account.from_key(configs.PRIVATE_KEY)

CHAIN_ID = 56
CHI_ABI = json.load(open('abis/ICHI.json'))
WETH_ABI = json.load(open('abis/IWETH9.json'))
ERC_20_ABI = json.load(open('abis/IERC20.json'))


CHI = Token(CHAIN_ID, '0x0000000000004946c0e9F43F4Dee607b0eF1fA1c', 'CHI', 0, CHI_ABI, web3)
WBNB = Token(CHAIN_ID, '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c', 'WBNB', 18, WETH_ABI, web3)
USDT = Token(CHAIN_ID, '0x55d398326f99059fF775485246999027B3197955', 'USDT', 18, ERC_20_ABI, web3)
DOT = Token(CHAIN_ID, '0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402', 'DOT', 18, ERC_20_ABI, web3)
BUSD = Token(CHAIN_ID, '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56', 'BUSD', 18, ERC_20_ABI, web3)
USDC = Token(CHAIN_ID, '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d', 'USDC', 18, ERC_20_ABI, web3)


def load_contract(name: str, test: bool = True) -> Contract:
    path = f'build/contracts/{name}.json' if test else f'deployed_contracts/{name}.json'
    return tools.transaction.load_contract(path)


def mint_chi(amount: int) -> str:
    try:
        tx_hash = tools.transaction.sign_and_send_contract_tx(
            CHI.contract.functions.mint,
            amount,
            max_gas_=38_000_000,
            wait_finish_=True,
            account_=account,
        )
    except Exception as e:
        log.warning(f'CHI mint failed: {e}')
    else:
        log.info(f'Minted {amount} CHI')
    return tx_hash


def wrap_currency(amount: int) -> str:
    try:
        tx_hash = tools.transaction.sign_and_send_contract_tx(
            WBNB.contract.functions.deposit,
            wait_finish_=True,
            account_=account,
            value_=amount,
        )
    except Exception as e:
        log.warning(f'BNB wrapping failed: {e}')
    else:
        log.info(f'Wrapped {amount} BNB')
    return tx_hash


def withdraw_token(contract: Contract, token: Union[str, Token]) -> str:
    address = token.address if isinstance(token, Token) else web3.toChecksumAddress(token)
    try:
        tx_hash = tools.transaction.sign_and_send_contract_tx(
            contract.functions.withdrawToken,
            address,
            wait_finish_=True,
            account_=account,
        )
    except Exception as e:
        log.warning(f'Withdraw failed: {e}')
    else:
        log.info(f'Withdrew {token} from {contract}')
    return tx_hash


def transfer_tokens(address: Union[str, Contract], token_amount: TokenAmount) -> str:
    address = address.address if isinstance(address, Contract) else web3.toChecksumAddress(address)
    amount = token_amount.amount
    contract = token_amount.token.contract
    try:
        tx_hash = tools.transaction.sign_and_send_contract_tx(
            contract.functions.transfer,
            address,
            amount,
            wait_finish_=True,
            account_=account,
        )
    except Exception as e:
        log.warning(f'Transfer failed: {e}')
    else:
        log.info(f'Sent {token_amount} to {address}')
    return tx_hash


def load_dexes(
    dex_protocols: dict[str, Type[DexProtocol]],
    address_directory: Union[str, pathlib.Path],
    load_removed: bool = True,
) -> dict[str, DexProtocol]:
    return PairManager.load_dex_protocols(address_directory, dex_protocols, web3, load_removed)
