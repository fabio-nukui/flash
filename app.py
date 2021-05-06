import importlib
import logging

import configs
import tools
from startup import setup

log = logging.getLogger(__name__)


def main():
    strategy = importlib.import_module(f'strategies.{configs.STRATEGY}')
    while not tools.process.is_shutting_down:
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
