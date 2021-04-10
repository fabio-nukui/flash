import logging

from web3 import HTTPProvider, IPCProvider, Web3, WebsocketProvider
from web3.middleware import geth_poa_middleware

import configs

log = logging.getLogger(__name__)


def from_uri(endpoint_uri: str, warn_http_provider: bool = True) -> Web3:
    middlewares = []
    if configs.POA_CHAIN:
        middlewares.append(geth_poa_middleware)

    if endpoint_uri.startswith('http'):
        if warn_http_provider:
            log.warning('HTTPProvider does not support filters')
        provider = HTTPProvider(endpoint_uri)
    elif endpoint_uri.startswith('wss'):
        provider = WebsocketProvider(endpoint_uri)
    elif endpoint_uri.endswith('ipc'):
        provider = IPCProvider(endpoint_uri)
    else:
        raise ValueError(f'Invalid {endpoint_uri=}')
    return Web3(provider, middlewares)


def get_web3(verbose: bool = False, force_local: bool = configs.FORCE_LOCAL_RCP_CONNECTION) -> Web3:
    if force_local:
        web3_remote = from_uri('wss://dummy.com')
    else:
        web3_remote = from_uri(configs.RCP_REMOTE_URI)
    web3_local = from_uri(configs.RCP_LOCAL_URI)

    try:
        last_block_remote = web3_remote.eth.block_number
    except Exception:
        last_block_remote = None

    try:
        last_block_local = web3_local.eth.block_number
    except Exception:
        last_block_local = None

    if last_block_local is None and last_block_remote is None:
        raise Exception('No available RCP connection')
    elif last_block_local is None and last_block_remote is not None:
        if verbose:
            log.info('Using remote RCP endpoint')
        web3 = web3_remote
    elif last_block_local is not None and last_block_remote is None:
        if verbose:
            log.info('Using local RCP endpoint')
        web3 = web3_local
    elif (n := last_block_remote - last_block_local) > 1:
        if verbose:
            log.info(f'Local RCP endpoint behind by {n} blocks, using remote endpoint')
        web3 = web3_remote
    else:
        if verbose:
            log.info('Using local RCP endpoint')
        web3 = web3_local

    if verbose:
        log.info(f'Running on chain_id={configs.CHAIN_ID}')
        log.info(f'Latest block: {web3.eth.block_number}')

    return web3
