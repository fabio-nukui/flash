import logging
import time
from datetime import datetime
from random import random

import configs
import tools

log = logging.getLogger(__name__)

MIN_BNB_BALANCE = 0.03
IRON_VAULT_ADDRESS = '0xEf8803b4c9600d7F0991654732Be306337de84b9'
MIN_SECONDS_HARVEST = 3600 * 7
MAX_SECONDS_HARVEST = 3600 * 9
SELECTOR_HARVEST_ALL_STRATEGIES = '0x1997db76'
SELECTOR_TIMESTAMP_LAST_HARVEST = '0xa44c00da'


def get_wake_up_interval(seconds_from_last_harvest):
    return max(
        0,
        MIN_SECONDS_HARVEST
        + (MAX_SECONDS_HARVEST - MIN_SECONDS_HARVEST) * random()
        - seconds_from_last_harvest
    )


def run():
    web3 = tools.w3.get_web3()
    tx_harvest = {
        'from': configs.ADDRESS,
        'to': IRON_VAULT_ADDRESS,
        'data': SELECTOR_HARVEST_ALL_STRATEGIES,
        'gas': 1_500_000,
    }
    tx_last_timestamp = {
        'to': IRON_VAULT_ADDRESS,
        'data': SELECTOR_TIMESTAMP_LAST_HARVEST,
    }

    while web3.eth.get_balance(configs.ADDRESS) > MIN_BNB_BALANCE * 10 ** 18:
        timestamp_last_harvest = int.from_bytes(web3.eth.call(tx_last_timestamp), 'big')
        seconds_from_last_harvest = datetime.now().timestamp() - timestamp_last_harvest
        log.info(f'{seconds_from_last_harvest:.1f} seconds from last harvest')
        if seconds_from_last_harvest > MIN_SECONDS_HARVEST:
            log.info('Harvesting strategy')
            tools.transaction.sign_and_send_tx(tx_harvest, web3, wait_finish=True)
            seconds_from_last_harvest = 0
        interval = get_wake_up_interval(seconds_from_last_harvest)
        log.info(f'Sleeping for {interval:.1f} seconds')
        time.sleep(interval)
    log.info('Balance less than minimum')
