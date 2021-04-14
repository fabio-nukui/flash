# Runs housekeeping functions such as withdrawing funds from contracts
import json
import logging
import os
import time
from typing import Iterable

from web3 import Web3
from web3.contract import Contract

import configs
import tools
from core import Token, TokenAmount
from dex import PancakeswapDex, ValueDefiSwapDex
from dex.base import DexProtocol
from strategies import pcs_vds_v1

log = logging.getLogger(__name__)

ERC20_ABI = json.load(open('abis/IERC20.json'))
MIN_ETHERS_WITHDRAW_CONVERT = 0.05  # About 50x the transaction fees on transfer + swap
MAX_SLIPPAGE = 0.4
WRAPPED_CURRENCY_TOKEN = tools.price.get_wrapped_currency_token()
RUN_INTERVAL = 3600
RUNNING_STRATEGIES = os.environ['RUNNING_STRATEGIES'].split(',')
MIN_CONFIRMATIONS = 2
WETH_ABI = json.load(open('abis/IWETH9.json'))


def get_currency_symbol():
    if configs.CHAIN_ID == 1:
        return 'ETH'
    if configs.CHAIN_ID == 56:
        return 'BNB'
    return ''


def get_address_balances(address: str, tokens: list[Token]) -> list[TokenAmount]:
    amounts = []
    for token in tokens:
        amount = token.contract.functions.balanceOf(address).call()
        amounts.append(TokenAmount(token, amount))
    return amounts


def get_address_balances_in_native_currency(
    address: str,
    tokens: list[Token],
) -> list[tuple[TokenAmount, float]]:
    balances = []
    for token_amount in get_address_balances(address, tokens):
        if not token_amount.amount:
            ethers_amount = 0.0
        elif token_amount.token == WRAPPED_CURRENCY_TOKEN:
            ethers_amount = token_amount.amount_in_units
        else:
            quote_1inch = tools.exchange.get_quote_1inch(token_amount)
            ethers_amount = quote_1inch / 10 ** WRAPPED_CURRENCY_TOKEN.decimals
        balances.append((token_amount, ethers_amount))
    return balances


class Strategy:
    def __init__(self, contract: Contract, list_dex: list[DexProtocol], name: str):
        self.web3 = contract.web3
        self.contract = contract
        self.list_dex = list_dex
        self.name = name

        self.tokens = list({token for dex in list_dex for token in dex.tokens})

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name})'

    def withdraw_tokens(self):
        balances = get_address_balances_in_native_currency(self.contract.address, self.tokens)
        amounts_withdraw = [
            token_amount
            for token_amount, native_amount in balances
            if native_amount >= MIN_ETHERS_WITHDRAW_CONVERT
        ]
        if not amounts_withdraw:
            log.info(f'{self}: No tokens to withdraw')
            return
        for token_amount in amounts_withdraw:
            log.info(f'{self}: Withdrawing {token_amount}')
            tools.contracts.sign_and_send_contract_transaction(
                self.contract.functions.withdrawToken,
                token_amount.token.address,
                wait_finish_=True
            )
        log.info(f'{self}: Finished withdrawing tokens from contract')


def convert_amounts(tokens: Iterable[Token], web3: Web3):
    balances = get_address_balances_in_native_currency(configs.ADDRESS, tokens)
    amounts_withdraw = [
        token_amount
        for token_amount, native_amount in balances
        if native_amount >= MIN_ETHERS_WITHDRAW_CONVERT
    ]
    if not amounts_withdraw:
        log.info('No tokens to convert')
        return
    for token_amount in amounts_withdraw:
        log.info(f'Converting {token_amount}')
        if token_amount.token == WRAPPED_CURRENCY_TOKEN:  # WBNB / WETH
            contract = web3.eth.contract(token_amount.token.address, abi=WETH_ABI)
            tools.contracts.sign_and_send_contract_transaction(
                contract.functions.withdraw,
                token_amount.amount,
                wait_finish_=True
            )
        else:
            tools.exchange.exchange_1inch(
                web3,
                token_amount,
                max_slippage=MAX_SLIPPAGE,
                wait_finish=True
            )
        log.info('Finished converting tokens from deployer address')


def get_strategy(strategy_name: str, web3: Web3):
    if strategy_name == 'pcs_vds_v1':
        with open(pcs_vds_v1.ADDRESS_FILEPATH) as f:
            addresses = json.load(f)
            pcs_dex = PancakeswapDex(pairs_addresses=addresses['pcs_dex'], web3=web3)
            vds_dex = ValueDefiSwapDex(pairs_addresses=addresses['vds_dex'], web3=web3)
        contract = tools.contracts.load_contract(pcs_vds_v1.CONTRACT_DATA_FILEPATH)
        return Strategy(contract, [pcs_dex, vds_dex], strategy_name)


def run():
    web3 = tools.w3.get_web3(verbose=True)
    strategies = [get_strategy(name, web3) for name in RUNNING_STRATEGIES]
    all_tokens = {token for strategy in strategies for token in strategy.tokens}
    while True:
        for strategy in strategies:
            strategy.withdraw_tokens()
        convert_amounts(all_tokens, web3)
        balance = web3.eth.get_balance(configs.ADDRESS)
        log.info(f'Account balance: {balance / 10 ** 18} {get_currency_symbol()}')
        time.sleep(RUN_INTERVAL)
