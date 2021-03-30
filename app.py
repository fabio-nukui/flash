import importlib
import logging

from web3 import Web3
from web3.middleware import geth_poa_middleware

import configs


def main():
    if configs.RCP_ENDPOINT.startswith('http'):
        from web3 import HTTPProvider
        web3 = Web3(HTTPProvider(configs.RCP_ENDPOINT))
    elif configs.RCP_ENDPOINT.startswith('wss'):
        from web3 import WebsocketProvider
        web3 = Web3(WebsocketProvider(configs.RCP_ENDPOINT))
    else:
        raise Exception(f'Invalid RCP_ENDPOINT {configs.RCP_ENDPOINT}')
    logging.info(f'Starting web3 provider using {configs.RCP_ENDPOINT}')

    if configs.CHAIN_ID == 56:
        # Binance Smart Chain uses PoA
        web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    logging.info(f'Running on chain_id={configs.CHAIN_ID}')
    latest_block = web3.eth.getBlock('latest')['number']
    logging.info(f'Latest block: {latest_block}')

    strategy = importlib.import_module(f'strategies.{configs.STRATEGY}')
    logging.info(f'Starting strategy {configs.STRATEGY}')

    strategy.run(web3)


if __name__ == '__main__':
    main()
