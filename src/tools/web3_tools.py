from web3 import HTTPProvider, IPCProvider, Web3, WebsocketProvider
from web3.middleware import geth_poa_middleware

import configs
from tools.logger import log


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
