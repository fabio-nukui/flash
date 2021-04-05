import json
import random
import time
import traceback
from concurrent import futures
from threading import Lock, Thread

from eth_account.datastructures import SignedTransaction
from web3 import Account, Web3
from web3.contract import Contract, ContractFunction

import configs
from tools import web3_tools
from tools.logger import log

ACCOUNT = Account.from_key(configs.PRIVATE_KEY)
CONNECTION_KEEP_ALIVE_TIME_INTERVAL = 30


class BackgroundWeb3:
    def __init__(self, uri: str):
        self.uri = uri
        self.web3 = web3_tools.from_uri(uri, warn_http_provider=False)
        self.lock = Lock()
        self._thread: Thread
        self._keep_alive()

    def send_transaction(self, tx: SignedTransaction):
        if not self.is_alive():
            return
        with futures.ThreadPoolExecutor(1) as pool:
            pool.submit(self._send_transaction, tx)

    def is_alive(self):
        return self._thread.is_alive()

    def _send_transaction(self, tx: SignedTransaction) -> str:
        try:
            with self.lock:
                tx_hash = self.web3.eth.send_raw_transaction(tx.rawTransaction).hex()
            log.debug(f'Sent transaction using {self.uri}')
            return tx_hash
        except Exception:
            log.info(f'{self.uri!r} failed to send transaction')
            log.debug(traceback.format_exc())
            return '0x0'

    def _keep_alive(self):
        self._thread = Thread(target=self._heartbeat, args=(self.web3,), daemon=True)
        self._thread.start()

    def _heartbeat(self):
        while True:
            time.sleep(CONNECTION_KEEP_ALIVE_TIME_INTERVAL + random.random())
            try:
                with self.lock:
                    block_number = self.web3.eth.block_number
                log.debug(f'Connection {self.uri} on {block_number=}')
            except Exception:
                log.info(f'{self.uri!r} failed to send last block')
                log.info(traceback.format_exc())
                break


def load_contract(contract_data_filepath: str, web3: Web3) -> Contract:
    """Load contract and add "sign_and_call" method to its functions"""
    with open(contract_data_filepath) as f:
        data = json.load(f)
    address = data['networks'][str(configs.CHAIN_ID)]['address']
    abi = data['abi']

    return web3.eth.contract(address, abi=abi)


def multi_broadcast_transaction(tx: SignedTransaction):
    for bg_web3 in LIST_BG_WEB3:
        bg_web3.send_transaction(tx)


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
        multi_broadcast_transaction(tx)

    return web3.eth.send_raw_transaction(signed_tx.rawTransaction).hex()


def _get_providers() -> list[BackgroundWeb3]:
    if not configs.MULTI_BROADCAST_TRANSACTIONS:
        return []
    endpoints = json.load(open('addresses/public_rcp_endpoints.json'))[str(configs.CHAIN_ID)]
    endpoints.append(configs.RCP_REMOTE_URI)

    return [BackgroundWeb3(uri) for uri in endpoints]


LIST_BG_WEB3 = _get_providers()
