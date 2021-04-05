import importlib

from web3 import Web3

import configs
from startup import setup
from tools import web3_tools
from tools.logger import log


def get_web3() -> Web3:
    web3_remote = web3_tools.from_uri(configs.RCP_REMOTE_URI)
    web3_local = web3_tools.from_uri(configs.RCP_LOCAL_URI)

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
        log.info('Using remote RCP endpoint')
        web3 = web3_remote
    elif last_block_local is not None and last_block_remote is None:
        log.info('Using local RCP endpoint')
        web3 = web3_local
    elif (n := last_block_remote - last_block_local) > 1:
        log.info(f'Local RCP endpoint behind by {n} blocks, using remote endpoint')
        web3 = web3_remote
    else:
        log.info('Using local RCP endpoint')
        web3 = web3_local

    log.info(f'Running on chain_id={configs.CHAIN_ID}')
    latest_block = web3.eth.block_number
    log.info(f'Latest block: {latest_block}')

    return web3


def main():
    strategy = importlib.import_module(f'strategies.{configs.STRATEGY}')
    while True:
        try:
            web3 = get_web3()
            log.info(f'Starting strategy {configs.STRATEGY}')
            strategy.run(web3)
        except Exception as e:
            log.error('Error during strategy execution')
            log.exception(e)
            log.info('Restarting strategy')


if __name__ == '__main__':
    setup()
    main()
