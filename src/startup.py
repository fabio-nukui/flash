# General script configuration to be run at service start
import logging.config
import warnings

import yaml

import configs
from tools import contracts


def setup_warnings():
    warnings.simplefilter(action='ignore', category=FutureWarning)
    warnings.simplefilter(action='ignore', category=UserWarning, append=True)
    warnings.simplefilter(action='ignore', category=DeprecationWarning, append=True)


def setup_logger():
    dict_config = yaml.safe_load(open('logging_config.yaml'))
    dict_config['handlers']['logfile']['filename'] = f'logs/{configs.STRATEGY}.log'
    dict_config['handlers']['watchtower']['stream_name'] = \
        f'{configs.STRATEGY}-{{strftime:%y-%m-%d}}'
    if not configs.LOG_AWS:
        del dict_config['handlers']['watchtower']
        dict_config['root']['handlers'].remove('watchtower')

    dict_config['loggers']['tools.cache'] = {'level': configs.CACHE_LOG_LEVEL}
    logging.config.dictConfig(dict_config)


def setup():
    setup_warnings()
    setup_logger()
    contracts.setup()
