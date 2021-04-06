import importlib

import configs
from startup import setup
from tools.logger import log


def main():
    strategy = importlib.import_module(f'strategies.{configs.STRATEGY}')
    while True:
        try:
            log.info(f'Starting strategy {configs.STRATEGY}')
            strategy.run()
        except Exception as e:
            log.error('Error during strategy execution')
            log.exception(e)
            log.info('Restarting strategy')


if __name__ == '__main__':
    setup()
    main()
