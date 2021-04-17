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

RUNNING_STRATEGIES = os.environ['RUNNING_STRATEGIES'].split(',')
MIN_CONFIRMATIONS = 2
MIN_ETHERS_WITHDRAW_CONVERT = 0.05  # About 50x the transaction fees on transfer + swap
MAX_SLIPPAGE = 0.4
RUN_INTERVAL = 300

# $5.000 reserve allow for arbitrage operation of $10.000 gross profit at 50% share of gas
NATIVE_CURRENCY_USD_RESERVE = 5_000
CHI_MIN_CONTRACT_RESERVE = 200
CHI_CONTRACT_TOP_UP = 1000

ERC20_ABI = json.load(open('abis/IERC20.json'))
WETH_ABI = json.load(open('abis/IWETH9.json'))
CHI_ABI = json.load(open('abis/ICHI.json'))
WRAPPED_CURRENCY_TOKEN = tools.price.get_wrapped_currency_token()
NATIVE_CURRENCY_SYMBOL = tools.price.get_native_token_symbol()
with open('addresses/strategies/housekeeper.json') as f:
    addresses = json.load(f)[str(configs.CHAIN_ID)]
    STABLE_RESERVE_TOKEN_DATA = addresses['stable_reserve_token']
    CHI_TOKEN_DATA = addresses['chi_token']


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
            ethers_amount = quote_1inch / 10 ** tools.price.get_native_token_decimals()
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

    def top_up_chi(self, chi_token: Token):
        chi_balance = chi_token.contract.functions.balanceOf(self.contract.address).call()
        log.info(f'{self}: CHI balance: {chi_balance}')
        if chi_balance > CHI_MIN_CONTRACT_RESERVE:
            return
        if chi_token.contract.functions.balanceOf(configs.ADDRESS).call() < CHI_CONTRACT_TOP_UP:
            log.info('Buying CHI')
            amount_chi = TokenAmount(chi_token, CHI_CONTRACT_TOP_UP)
            native_amount = tools.exchange.get_quote_1inch(amount_chi)
            tools.exchange.exchange_1inch(
                self.web3,
                native_amount,
                chi_token,
                max_slippage=MAX_SLIPPAGE,
                wait_finish=True
            )
        amount_transfer = min(
            chi_token.contract.functions.balanceOf(configs.ADDRESS).call(), CHI_CONTRACT_TOP_UP)
        log.info(f'Transfering {amount_transfer} CHI')
        tools.contracts.sign_and_send_contract_transaction(
            chi_token.contract.functions.transfer,
            self.contract.address,
            amount_transfer,
            wait_finish_=True,
        )


def get_deployer_balance_usd(web3: Web3) -> float:
    balance = web3.eth.get_balance(configs.ADDRESS) / 10 ** tools.price.get_native_token_decimals()
    return balance * tools.price.get_price_usd_native_token(web3)


def convert_amounts_native(amounts_withdraw: Iterable[TokenAmount], web3: Web3):
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


def convert_amounts_stable(
    amounts_withdraw: Iterable[TokenAmount],
    stable_reserve_token: Token,
    web3: Web3
):
    for token_amount in amounts_withdraw:
        log.info(f'Converting {token_amount}')
        tools.exchange.exchange_1inch(
            web3,
            token_amount,
            stable_reserve_token,
            max_slippage=MAX_SLIPPAGE,
            wait_finish=True
        )


def convert_amounts(tokens: Iterable[Token], stable_reserve_token: Token, web3: Web3):
    balances = get_address_balances_in_native_currency(configs.ADDRESS, tokens)
    amounts_withdraw = [
        token_amount
        for token_amount, native_amount in balances
        if native_amount >= MIN_ETHERS_WITHDRAW_CONVERT
    ]
    if not amounts_withdraw:
        log.info('No tokens to convert')
        return
    if get_deployer_balance_usd(web3) < NATIVE_CURRENCY_USD_RESERVE:
        log.info(f'Converting to {NATIVE_CURRENCY_SYMBOL}')
        convert_amounts_native(amounts_withdraw, web3)
    else:
        log.info(f'Converting to {stable_reserve_token.symbol}')
        convert_amounts_stable(amounts_withdraw, stable_reserve_token, web3)
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
    stable_reserve_token = Token(chain_id=configs.CHAIN_ID, web3=web3, **STABLE_RESERVE_TOKEN_DATA)
    chi_token = Token(chain_id=configs.CHAIN_ID, web3=web3, **CHI_TOKEN_DATA)

    strategies = [get_strategy(name, web3) for name in RUNNING_STRATEGIES]
    all_tokens = {token for strategy in strategies for token in strategy.tokens}
    while True:
        for strategy in strategies:
            strategy.withdraw_tokens()
            strategy.top_up_chi(chi_token)
        convert_amounts(all_tokens, stable_reserve_token, web3)

        balance_native = web3.eth.get_balance(configs.ADDRESS)
        balance_native_units = balance_native / 10 ** tools.price.get_native_token_decimals()

        balance_stable = stable_reserve_token.contract.functions.balanceOf(configs.ADDRESS).call()
        balance_stable_units = balance_stable / 10 ** stable_reserve_token.decimals

        log.info(
            f'Account balance: {balance_native_units:.6f} {NATIVE_CURRENCY_SYMBOL}; '
            f'{balance_stable_units:.2f} {stable_reserve_token.symbol}'
        )
        time.sleep(RUN_INTERVAL)
