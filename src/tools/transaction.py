from __future__ import annotations

import json
import logging
import random
import time
import traceback
from concurrent import futures
from threading import Lock, Thread

from eth_account.datastructures import SignedTransaction
from web3 import Account, Web3
from web3.contract import Contract, ContractFunction
from web3.exceptions import TransactionNotFound

import configs
from tools import price, w3

log = logging.getLogger(__name__)

PUBLIC_ENDPOINTS_FILEPATH = 'addresses/public_rpc_endpoints.json'
LIST_BG_WEB3: list[BackgroundWeb3] = []
ACCOUNT = Account.from_key(configs.PRIVATE_KEY)
ACCOUNT_TX_COUNTER: TransactionCounter = None
TX_WAIT_POLL_INTERVAL = 0.01
TX_COUNTER_POLL_INTERVAL = 1.0
MAX_SECONDS_TX_COUNTER_STAY_AHEAD = 30

CONNECTION_KEEP_ALIVE_TIME_INTERVAL = 30
MAX_BLOCKS_WAIT_RECEIPT = 20
CHI_FLAG = 'chiFlag'


class BackgroundWeb3:
    def __init__(self, uri: str, verbose: bool = False):
        self.uri = uri
        self.verbose = verbose
        self.web3 = w3.from_uri(uri)
        self._executor = futures.ThreadPoolExecutor(1)
        self._heartbeat_thread: Thread
        if not uri == configs.RPC_LOCAL_URI:
            self._keep_alive()

    def send_transaction(self, tx: SignedTransaction):
        if not self.is_alive():
            return
        self._executor.submit(self._send_transaction, tx)

    def is_alive(self):
        if self.uri == configs.RPC_LOCAL_URI:
            return True
        return self._heartbeat_thread.is_alive()

    def _send_transaction(self, tx: SignedTransaction):
        try:
            self.web3.eth.send_raw_transaction(tx.rawTransaction)
            log.debug(f'Sent transaction using {self.uri}')
        except Exception:
            if self.uri == configs.RPC_LOCAL_URI:
                log.warning(f'{self.uri!r} failed to send transaction')
                log.debug(traceback.format_exc())

    def _keep_alive(self):
        log.debug(f'Keep-alive: {self.uri}')
        self._heartbeat_thread = Thread(target=self._heartbeat, daemon=True)
        self._heartbeat_thread.start()

    def _heartbeat(self):
        while True:
            time.sleep(CONNECTION_KEEP_ALIVE_TIME_INTERVAL + random.random())
            try:
                future = self._executor.submit(getattr, self.web3.eth, 'block_number')
                block_number = future.result()
                if self.verbose:
                    log.debug(f'Connection {self.uri} on {block_number=}')
            except Exception:
                if self.uri == configs.RPC_LOCAL_URI:
                    log.warning(f'{self.uri!r} failed to send last block')
                    log.warning(traceback.format_exc())


class TransactionCounter:
    def __init__(
        self,
        address: str,
        web3: Web3,
        poll_interval: float = TX_COUNTER_POLL_INTERVAL,
    ):
        self.address = address
        self.web3 = web3
        self.poll_interval = poll_interval
        self.max_checks_stay_ahead = round(MAX_SECONDS_TX_COUNTER_STAY_AHEAD / poll_interval)

        self.lock = Lock()
        self._count = web3.eth.get_transaction_count(address)
        self._n_checks_stay = 0

        self._tread = Thread(target=self._keep_count_updated, daemon=True)
        self._tread.start()

    def reset(self):
        count = self.web3.eth.get_transaction_count(self.address)
        if self._count != count:
            with self.lock:
                self._count = count

    def _keep_count_updated(self):
        while True:
            try:
                time.sleep(self.poll_interval)
                count = self.web3.eth.get_transaction_count(self.address)
                if self.count > count:
                    self._n_checks_stay += 1
                    if self._n_checks_stay > self.max_checks_stay_ahead:
                        self._n_checks_stay = 0
                        with self.lock:
                            self._count = count
                else:
                    self._n_checks_stay = 0
                    if self._count < count:
                        with self.lock:
                            self._count = count
            except Exception:
                log.debug('TransactionCounter listener failed, restarting in 1 sec')
                time.sleep(1)

    def get_nonce(self):
        with self.lock:
            self._count += 1
            return self._count - 1

    @property
    def count(self):
        with self.lock:
            return self._count


def load_contract(contract_data_filepath: str, web3: Web3 = None) -> Contract:
    """Load contract and add "sign_and_call" method to its functions"""
    web3 = w3.get_web3() if web3 is None else web3
    with open(contract_data_filepath) as f:
        data = json.load(f)
    address = data['networks'][str(configs.CHAIN_ID)]['address']
    abi = data['abi']

    return web3.eth.contract(address, abi=abi)


def broadcast_tx(tx: SignedTransaction):
    for bg_web3 in LIST_BG_WEB3:
        bg_web3.send_transaction(tx)


def _has_chi_flag(func: ContractFunction):
    function_inputs = [e for e in func.contract_abi if e.get('name') == func.fn_name][0]['inputs']
    return any(fn_input.get('name') == CHI_FLAG for fn_input in function_inputs)


def get_nonce(address: str, web3: Web3, dry_run: bool = False):
    if address != ACCOUNT.address:
        return web3.eth.get_transaction_count(address)
    if dry_run:
        return ACCOUNT_TX_COUNTER.count
    return ACCOUNT_TX_COUNTER.get_nonce()


def sign_and_send_tx(
    tx: dict,
    web3: Web3,
    wait_finish: bool = False,
    max_blocks_wait: int = None,
    account: Account = None,
    verbose: bool = False,
) -> str:
    account = ACCOUNT if account is None else account
    tx['gas'] = tx.get('gas', 1_000_000)

    # Do not use dict get() with default, or it will update nonce unnecessarily
    tx['nonce'] = tx['nonce'] if 'nonce' in tx else get_nonce(account.address, web3)
    tx['gasPrice'] = tx['gasPrice'] if 'gasPrice' in tx else price.get_gas_price()

    signed_tx = account.sign_transaction(tx)
    tx_hash = signed_tx.hash.hex()
    log.debug(f'Sending transaction {tx_hash}: {tx}')
    broadcast_tx(signed_tx)

    if wait_finish:
        wait_tx_finish(tx_hash, web3, max_blocks_wait, verbose)
    return tx_hash


def dry_run_contract_tx(
    func: ContractFunction,
    *args,
    account_: Account = None,
    value_: int = 0,
    gas_price_: int = None,
    max_gas_: int = 1_000_000,
    **kwargs,
) -> str:
    web3 = func.web3
    account = ACCOUNT if account_ is None else account_
    gas_price_ = price.get_gas_price() if gas_price_ is None else gas_price_

    tx = func(*args, **kwargs).buildTransaction({
        'from': account.address,
        'value': value_,
        'chainId': configs.CHAIN_ID,
        'gas': max_gas_,
        'nonce': get_nonce(account.address, web3, dry_run=True),
        'gasPrice': gas_price_,
    })
    return web3.eth.call(tx, block_identifier=configs.BLOCK).hex()


def sign_and_send_contract_tx(
    func: ContractFunction,
    *args,
    account_: Account = None,
    value_: int = 0,
    gas_price_: int = None,
    max_gas_: int = 1_000_000,
    wait_finish_: bool = False,
    max_blocks_wait_: int = None,
    **kwargs,
) -> str:
    web3 = func.web3
    account = ACCOUNT if account_ is None else account_
    gas_price_ = price.get_gas_price() if gas_price_ is None else gas_price_
    if _has_chi_flag(func) and kwargs.get(CHI_FLAG) is not None:
        kwargs[CHI_FLAG] = 0 if gas_price_ < 2 * price.get_gas_price() else 1

    tx = func(*args, **kwargs).buildTransaction({
        'from': account.address,
        'value': value_,
        'chainId': configs.CHAIN_ID,
        'gas': max_gas_,
        'nonce': get_nonce(account.address, web3),
        'gasPrice': gas_price_,
    })
    return sign_and_send_tx(tx, web3, wait_finish_, max_blocks_wait_, account)


def wait_tx_finish(
    tx_hash: str,
    web3: Web3,
    max_blocks_wait: int = None,
    verbose: bool = False,
    min_confirmations: int = 1,
):
    listener = w3.BlockListener(web3, poll_interval=TX_WAIT_POLL_INTERVAL)
    max_blocks_wait = max_blocks_wait or MAX_BLOCKS_WAIT_RECEIPT
    n = 0
    for current_block in listener.wait_for_new_blocks():
        try:
            receipt = web3.eth.getTransactionReceipt(tx_hash)
        except TransactionNotFound:
            n += 1
            if n >= max_blocks_wait:
                raise Exception(f'Transactio {tx_hash} not found after {n} blocks')
        else:
            if receipt.status == 0:
                log.info(f'Failed to send transaction: {tx_hash}')
                return
            if current_block - receipt.blockNumber >= (min_confirmations - 1):
                return


def _get_providers() -> list[BackgroundWeb3]:
    log.info(f'{configs.MULTI_BROADCAST_TRANSACTIONS=}')
    if configs.USE_REMOTE_RCP_CONNECTION:
        endpoints = [configs.RPC_LOCAL_URI, configs.RPC_REMOTE_URI]
    else:
        endpoints = [configs.RPC_LOCAL_URI]
    if configs.MULTI_BROADCAST_TRANSACTIONS:
        public_endpoints = json.load(open(PUBLIC_ENDPOINTS_FILEPATH))[str(configs.CHAIN_ID)]
        endpoints.extend(public_endpoints)

    return [BackgroundWeb3(uri) for uri in set(endpoints)]


def setup():
    global LIST_BG_WEB3
    global ACCOUNT_TX_COUNTER
    LIST_BG_WEB3 = _get_providers()
    ACCOUNT_TX_COUNTER = TransactionCounter(ACCOUNT.address, LIST_BG_WEB3[0].web3)
