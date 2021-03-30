# General script configuration to be run at service start
import logging
import sys
import warnings

import watchtower

import configs


def setup_warnings():
    warnings.simplefilter(action='ignore', category=FutureWarning)
    warnings.simplefilter(action='ignore', category=UserWarning, append=True)
    warnings.simplefilter(action='ignore', category=DeprecationWarning, append=True)


def setup_logger():
    log_format = '[%(asctime)s] %(name)s (%(filename)s:%(lineno)s) %(levelname)s: %(message)s'
    log_level = getattr(logging, configs.LOG_LEVEL)

    # These loggers are too verbose at DEBUG level. Set maximum level to WARNING
    for logger_name in ('botocore', 's3transfer', 'urllib3', 'hpack', 'httpx'):
        logger = logging.getLogger(logger_name)
        logger.setLevel(max(log_level, logging.WARNING))

    root_logger = logging.root
    root_logger.setLevel(log_level)
    formatter = logging.Formatter(log_format)

    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        root_logger.addHandler(console_handler)
    else:
        console_handler = root_logger.handlers[0]

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if configs.LOG_AWS is True:
        cloudwatch_handler = watchtower.CloudWatchLogHandler()
        cloudwatch_handler.setFormatter(formatter)
        root_logger.addHandler(cloudwatch_handler)


def setup():
    setup_warnings()
    setup_logger()
