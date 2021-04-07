import json
import logging
import random
import time
import traceback
from concurrent import futures
from threading import Thread

from eth_account.datastructures import SignedTransaction
from web3 import Account, Web3
from web3.contract import Contract, ContractFunction

import configs
import tools.w3

ACCOUNT = Account.from_key(configs.PRIVATE_KEY)
CONNECTION_KEEP_ALIVE_TIME_INTERVAL = 30
PUBLIC_ENDPOINTS_FILEPATH = 'addresses/public_rcp_endpoints.json'
log = logging.getLogger(__name__)


class BackgroundWeb3:
    def __init__(self, uri: str, verbose: bool = False):
        self.uri = uri
        self.verbose = verbose
        self._web3 = tools.w3.from_uri(uri, warn_http_provider=False)
        self._executor = futures.ThreadPoolExecutor(1)
        self._heartbeat_thread: Thread
        if not uri == configs.RCP_LOCAL_URI:
            self._keep_alive()

    def send_transaction(self, tx: SignedTransaction):
        if not self.is_alive():
            return
        self._executor.submit(self._send_transaction, tx)

    def is_alive(self):
        if self.uri == configs.RCP_LOCAL_URI:
            return True
        return self._heartbeat_thread.is_alive()

    def _send_transaction(self, tx: SignedTransaction):
        try:
            self._web3.eth.send_raw_transaction(tx.rawTransaction)
            log.debug(f'Sent transaction using {self.uri}')
        except Exception:
            log.info(f'{self.uri!r} failed to send transaction')
            log.debug(traceback.format_exc())

    def _keep_alive(self):
        log.debug(f'Keep-alive: {self.uri}')
        self._heartbeat_thread = Thread(target=self._heartbeat, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat(self):
        while True:
            time.sleep(CONNECTION_KEEP_ALIVE_TIME_INTERVAL + random.random())
            try:
                future = self._executor.submit(getattr, self._web3.eth, 'block_number')
                block_number = future.result()
                if self.verbose:
                    log.debug(f'Connection {self.uri} on {block_number=}')
            except Exception:
                log.debug(f'{self.uri!r} failed to send last block')
                log.debug(traceback.format_exc())


def load_contract(contract_data_filepath: str, web3: Web3 = None) -> Contract:
    """Load contract and add "sign_and_call" method to its functions"""
    web3 = tools.w3.get_web3() if web3 is None else web3
    with open(contract_data_filepath) as f:
        data = json.load(f)
    address = data['networks'][str(configs.CHAIN_ID)]['address']
    abi = data['abi']

    return web3.eth.contract(address, abi=abi)


def broadcast_transaction(tx: SignedTransaction):
    for bg_web3 in LIST_BG_WEB3:
        bg_web3.send_transaction(tx)


def sign_and_send_transaction(
    func: ContractFunction,
    *args,
    max_gas_: int = 1_000_000,
    gas_price_: int = None,
    **kwargs
) -> str:
    web3 = func.web3
    gas_price_ = tools.price.get_gas_price(web3) if gas_price_ is None else gas_price_
    tx = func(*args, **kwargs).buildTransaction({
        'from': ACCOUNT.address,
        'chainId': configs.CHAIN_ID,
        'gas': max_gas_,
        'nonce': web3.eth.get_transaction_count(ACCOUNT.address),
        'gasPrice': gas_price_
    })
    signed_tx = ACCOUNT.sign_transaction(tx)
    broadcast_transaction(signed_tx)

    return web3.sha3(signed_tx.rawTransaction).hex()


def _get_providers() -> list[BackgroundWeb3]:
    log.info(f'{configs.MULTI_BROADCAST_TRANSACTIONS=}')
    endpoints = [configs.RCP_LOCAL_URI, configs.RCP_REMOTE_URI]
    if configs.MULTI_BROADCAST_TRANSACTIONS:
        public_endpoints = json.load(open(PUBLIC_ENDPOINTS_FILEPATH))[str(configs.CHAIN_ID)]
        endpoints.extend(public_endpoints)

    return [BackgroundWeb3(uri) for uri in endpoints]


LIST_BG_WEB3 = _get_providers()
