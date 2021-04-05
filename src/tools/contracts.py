import asyncio
import json
import time
import traceback
from threading import Lock, Thread

from eth_account.datastructures import SignedTransaction
from web3 import Account, Web3
from web3.contract import Contract, ContractFunction

import configs
from tools import web3_tools
from tools.logger import log

ACCOUNT = Account.from_key(configs.PRIVATE_KEY)
CONNECTION_KEEP_ALIVE_TIME_INTERVAL = 60


def _get_providers() -> list[Web3]:
    endpoints = json.load(open('addresses/public_rcp_endpoints.json'))[str(configs.CHAIN_ID)]
    endpoints.append(configs.RCP_REMOTE_URI)

    return [
        web3_tools.from_uri(uri, warn_http_provider=False)
        for uri in endpoints
    ]


def _keep_provider_alive(web3: Web3):
    while True:
        try:
            time.sleep(CONNECTION_KEEP_ALIVE_TIME_INTERVAL)
            log.debug(f'Connection {web3.provider.endpoint_uri} on block {web3.eth.block_number}')
        except Exception:
            log.info(f'Connection {web3.provider.endpoint_uri!r} failed to send last block')
            log.info(traceback.format_exc())
            with PROVIDERS_LOCK:
                PROVIDERS.remove(web3)
                del web3
            break


async def _send_transaction(web3: Web3, tx: SignedTransaction) -> str:
    try:
        tx_hash = web3.eth.send_raw_transaction(tx.rawTransaction).hex()
        log.debug(f'Sent transaction using {web3.provider.endpoint_uri}')
        return tx_hash
    except Exception:
        log.info(f'Connection {web3.provider.endpoint_uri!r} failed to send transaction')
        log.info(traceback.format_exc())
        with PROVIDERS_LOCK:
            PROVIDERS.remove(web3)
            del web3
        return '0x0'


async def _send_transactions(tx: SignedTransaction) -> list[str]:
    with PROVIDERS_LOCK:
        tasks = [_send_transaction(web3, tx) for web3 in PROVIDERS]
    return await asyncio.gather(*tasks)


def _send_transactions_sync(tx: SignedTransaction):
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_send_transactions(tx))


def multi_broadcast_transaction(tx: SignedTransaction):
    Thread(target=_send_transactions_sync, args=(tx,)).start()


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
    func_call = func(*args, **kwargs)
    tx = func_call.buildTransaction({
        'from': ACCOUNT.address,
        'chainId': configs.CHAIN_ID,
        'gas': max_gas_,
        'nonce': web3.eth.get_transaction_count(ACCOUNT.address)
    })
    signed_tx = ACCOUNT.sign_transaction(tx)
    if configs.MULTI_BROADCAST_TRANSACTIONS:
        multi_broadcast_transaction(signed_tx)

    return web3.eth.send_raw_transaction(signed_tx.rawTransaction).hex()


if configs.MULTI_BROADCAST_TRANSACTIONS:
    PROVIDERS = _get_providers()
    PROVIDERS_LOCK = Lock()
    for provider in PROVIDERS:
        Thread(target=_keep_provider_alive, args=(provider,)).start()
else:
    PROVIDERS = []
