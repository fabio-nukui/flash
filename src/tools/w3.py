import logging
import time

from web3 import HTTPProvider, IPCProvider, Web3, WebsocketProvider
from web3.middleware import geth_poa_middleware

import configs
from tools import process

log = logging.getLogger(__name__)


def from_uri(endpoint_uri: str) -> Web3:
    middlewares = []
    if configs.POA_CHAIN:
        middlewares.append(geth_poa_middleware)

    if endpoint_uri.startswith('http'):
        provider = HTTPProvider(endpoint_uri)
    elif endpoint_uri.startswith('wss'):
        provider = WebsocketProvider(endpoint_uri)
    elif endpoint_uri.endswith('ipc'):
        provider = IPCProvider(endpoint_uri)
    else:
        raise ValueError(f'Invalid {endpoint_uri=}')
    return Web3(provider, middlewares)


def get_web3(verbose: bool = False, use_remote: bool = configs.USE_REMOTE_RCP_CONNECTION) -> Web3:
    if use_remote:
        web3_remote = from_uri(configs.RPC_REMOTE_URI)
    else:
        web3_remote = from_uri('wss://dummy.com')
    web3_local = from_uri(configs.RPC_LOCAL_URI)

    try:
        last_block_remote = web3_remote.eth.block_number
    except Exception:
        last_block_remote = None

    try:
        last_block_local = web3_local.eth.block_number
    except Exception:
        last_block_local = None

    if last_block_local is None and last_block_remote is None:
        raise Exception('No available RPC connection')
    elif last_block_local is None and last_block_remote is not None:
        if verbose:
            log.info('Using remote RPC endpoint')
        web3 = web3_remote
    elif last_block_local is not None and last_block_remote is None:
        if verbose:
            log.info('Using local RPC endpoint')
        web3 = web3_local
    elif (n := last_block_remote - last_block_local) > 1:
        if verbose:
            log.info(f'Local RPC endpoint behind by {n} blocks, using remote endpoint')
        web3 = web3_remote
    else:
        if verbose:
            log.info('Using local RPC endpoint')
        web3 = web3_local

    if verbose:
        log.info(f'Running on chain_id={configs.CHAIN_ID}')
        log.info(f'Latest block: {web3.eth.block_number}')

    return web3


class BlockListener:
    def __init__(
        self,
        web3: Web3 = None,
        block_label='latest',
        verbose: bool = True,
        poll_interval: float = configs.POLL_INTERVAL,
        update_block_config: bool = False,
    ):
        self.web3 = get_web3() if web3 is None else web3
        self.filter = self.web3.eth.filter(block_label)
        self.verbose = verbose
        self.poll_interval = poll_interval
        self.update_block_config = update_block_config

    def wait_for_new_blocks(self) -> int:
        while not process.is_shutting_down:
            entries = self.filter.get_new_entries()
            if len(entries) > 0:
                if len(entries) > 1:
                    log.warning(f'More than one block passed since last iteration ({len(entries)})')
                block_number = self.web3.eth.block_number
                if self.verbose:
                    log.debug(f'New block: {block_number}')
                if self.update_block_config:
                    configs.BLOCK = block_number
                yield block_number
            time.sleep(self.poll_interval)
        log.info('Stopped listener')
