import json

from web3 import Account, Web3
from web3.contract import Contract, ContractFunction

import configs

ACCOUNT = Account.from_key(configs.PRIVATE_KEY)


def load_contract(contract_data_filepath: str, web3: Web3) -> Contract:
    """Load contract and add "sign_and_call" method to its functions"""
    with open(contract_data_filepath) as f:
        data = json.load(f)
    address = data['networks'][str(configs.CHAIN_ID)]['address']
    abi = data['abi']

    return web3.eth.contract(address, abi=abi)


def sign_and_send_transaction(
    func: ContractFunction,
    *args,
    max_gas_: int = 1_000_000,
    **kwargs
) -> str:
    web3 = func.web3
    assert not (args and kwargs), 'Arguments must be all positional or keyword arguments, not both'
    func_call = func(*args, **kwargs)
    tx = func_call.buildTransaction({
        'from': ACCOUNT.address,
        'chainId': configs.CHAIN_ID,
        'gas': max_gas_,
        'nonce': web3.eth.get_transaction_count(ACCOUNT)
    })
    signed_tx = ACCOUNT.sign_transaction(tx)

    return web3.eth.send_raw_transaction(signed_tx.rawTransaction).hex()
