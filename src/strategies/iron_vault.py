import logging
import os
import time
from random import random

from web3 import Account

import tools

log = logging.getLogger(__name__)

MIN_BNB_BALANCE = 0.03
HOURS_PERIOD = 5


def run():
    web3 = tools.w3.get_web3()
    account = Account.from_key(os.environ['PK_2'])
    tx = {
        'from': account.address,
        'to': '0xEf8803b4c9600d7F0991654732Be306337de84b9',
        'data': '0x1997db76',
        'gas': 1_500_000,
    }

    while web3.eth.get_balance(account.address) > MIN_BNB_BALANCE * 10 ** 18:
        tools.transaction.sign_and_send_tx(tx, web3, wait_finish=True, account=account)
        time.sleep(HOURS_PERIOD * 3600 * (random() + 4.5) / 5)
    log.info('Balance less than minimum')
