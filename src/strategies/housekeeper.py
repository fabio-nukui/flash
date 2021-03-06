# Runs housekeeping functions such as withdrawing funds from contracts
import importlib
import json
import logging
import os
import time
from typing import Iterable

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import BadFunctionCallOutput

import configs
import tools
from arbitrage import PairManager
from core import LiquidityPair, Token, TokenAmount
from dex import DexProtocol
from exceptions import InsufficientLiquidity

log = logging.getLogger(__name__)

RUNNING_STRATEGIES = os.environ['RUNNING_STRATEGIES'].split(',')
N_BLOCKS_PRICE_CHANGE = int(os.environ['N_BLOCKS_PRICE_CHANGE'])
MIN_CONFIRMATIONS = 2
MIN_ETHERS_WITHDRAW = 0.1  # About 100x the transaction fees on transfer + swap
PRICE_CHANGE_WITHDRAW_IMPACT = 3  # At 3x, a 33% price decrease last 24h reduces min_withdraw to 0
MAX_SLIPPAGE = 0.4
RUN_INTERVAL = 60
DEFAULT_PRICE_CHANGE = -0.5  # By default, penalize tokens that we cannot extract prices

# $5.000 reserve allow for arbitrage operation of $20.000 gross profit at 25% share of gas
NATIVE_CURRENCY_USD_RESERVE = 5_000
CHI_MIN_CONTRACT_RESERVE = 300
CHI_CONTRACT_TOP_UP = 900
CHI_MINT_PRICE = 181530991848198  # Based on minting 600 CHI at 5.000000005 Gwei
CHI_MINT_MAX_GAS = 34_000_000

ERC20_ABI = json.load(open('abis/IERC20.json'))
WETH_ABI = json.load(open('abis/IWETH9.json'))
CHI_ABI = json.load(open('abis/ICHI.json'))
WRAPPED_CURRENCY_TOKEN = tools.price.get_wrapped_currency_token()
NATIVE_CURRENCY_SYMBOL = tools.price.get_native_token_symbol()
with open('addresses/strategies/housekeeper.json') as f:
    addresses = json.load(f)[str(configs.CHAIN_ID)]
    STABLE_RESERVE_TOKEN_DATA = addresses['stable_reserve_token']
    CHI_TOKEN_DATA = addresses['chi_token']

PREFERED_TOKENS_FILE = 'addresses/preferred_tokens.json'
TOKEN_MULTIPLIER_WEIGHT = 0.2
TOKEN_MULTIPLIERS = {
    Token(configs.CHAIN_ID, **data['token']): 1 + data['weight'] * TOKEN_MULTIPLIER_WEIGHT
    for data in json.load(open(PREFERED_TOKENS_FILE))[str(configs.CHAIN_ID)]
}

STRATEGIES_RESERVES = {
    'pcs_pcs2_v3': {WRAPPED_CURRENCY_TOKEN: 200 * 10 ** 18},  # 200 BNB for w-swaps
}


def get_address_balances(address: str, tokens: list[Token]) -> list[TokenAmount]:
    amounts = []
    for token in tokens:
        amount = token.contract.functions.balanceOf(address).call(block_identifier=configs.BLOCK)
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


def get_price_changes(
    tokens: list[Token],
    pools: list[LiquidityPair],
    web3: Web3
) -> list[float]:
    with tools.simulation.simulate_block(web3.eth.block_number - N_BLOCKS_PRICE_CHANGE):
        prices_24h = []
        for token in tokens:
            try:
                prices_24h.append(tools.price.get_price_usd(token, pools, web3))
            except BadFunctionCallOutput:  # In case token/pair didn't exist 24h ago
                prices_24h.append(0)
            except InsufficientLiquidity:  # Token lost liquidity
                prices_24h.append(0)

    prices_now = []
    for price_24h, token in zip(prices_24h, tokens):
        if price_24h == 0:
            prices_now.append(0)
        else:
            prices_now.append(tools.price.get_price_usd(token, pools, web3))
    return [
        (price_now / price_24h - 1) if price_24h != 0 else DEFAULT_PRICE_CHANGE
        for price_now, price_24h in zip(prices_now, prices_24h)
    ]


class Strategy:
    def __init__(self, contract: Contract, dexes: dict[str, DexProtocol], name: str):
        self.web3 = contract.web3
        self.contract = contract
        self.dexes = dexes
        self.name = name
        self.reserves: dict[Token, int] = STRATEGIES_RESERVES.get(self.name, {})

        self.tokens = list({token for dex in dexes.values() for token in dex.tokens})
        self.pools = [pool for dex in dexes.values() for pool in dex.pools]

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name})'

    def _adjust_for_reserve(self, token_amount: TokenAmount, native_amount: float):
        if token_amount.token not in self.reserves:
            return token_amount, native_amount
        adjusted_amount = token_amount - self.reserves[token_amount.token]
        if adjusted_amount < 0:
            return TokenAmount(token_amount.token, 0), 0.0
        return adjusted_amount, native_amount * adjusted_amount.amount / token_amount.amount

    def withdraw_tokens(self):
        balances = get_address_balances_in_native_currency(self.contract.address, self.tokens)
        price_changes = get_price_changes(self.tokens, self.pools, self.web3)
        amounts_withdraw = []
        for (token_amount, native_amount), price_change in zip(balances, price_changes):
            token_amount, native_amount = self._adjust_for_reserve(token_amount, native_amount)
            price_impact_on_withdraw = 1 + price_change * PRICE_CHANGE_WITHDRAW_IMPACT
            token_multiplier = TOKEN_MULTIPLIERS.get(token_amount.token, 1.0)
            min_withdraw = MIN_ETHERS_WITHDRAW * price_impact_on_withdraw * token_multiplier
            if native_amount > min_withdraw * max(min_withdraw, 0):
                amounts_withdraw.append(token_amount)
        if not amounts_withdraw:
            log.info(f'{self}: No tokens to withdraw')
            return
        for token_amount in amounts_withdraw:
            log.info(f'{self}: Withdrawing {token_amount}')
            tx_hash = tools.transaction.sign_and_send_contract_tx(
                self.contract.functions.withdrawToken,
                token_amount.token.address,
                wait_finish_=True
            )
            log.debug(f'{self}: Withdrew {token_amount} ({tx_hash})')
        log.info(f'{self}: Finished withdrawing tokens from contract')

    def top_up_chi(self, chi_token: Token):
        contract_balance = (
            chi_token.contract.functions.balanceOf(self.contract.address)
            .call(block_identifier=configs.BLOCK)
        )
        log.info(f'{self}: CHI balance: {contract_balance}')
        if contract_balance > CHI_MIN_CONTRACT_RESERVE:
            return
        deployer_balance = (
            chi_token.contract.functions.balanceOf(configs.ADDRESS)
            .call(block_identifier=configs.BLOCK)
        )
        if deployer_balance < CHI_CONTRACT_TOP_UP:
            log.info('Buying CHI')
            amount_chi = TokenAmount(chi_token, CHI_CONTRACT_TOP_UP)
            native_amount = tools.exchange.get_quote_1inch(amount_chi)
            price_chi = native_amount / CHI_CONTRACT_TOP_UP
            if price_chi > CHI_MINT_PRICE:
                tx_hash = tools.transaction.sign_and_send_contract_tx(
                    chi_token.contract.functions.mint,
                    CHI_CONTRACT_TOP_UP,
                    max_gas_=CHI_MINT_MAX_GAS,
                    wait_finish_=True,
                )
                log.debug(f'{self}: Minted CHI ({tx_hash})')
            else:
                tx_hash = tools.exchange.exchange_1inch(
                    self.web3,
                    native_amount,
                    chi_token,
                    max_slippage=MAX_SLIPPAGE,
                    wait_finish=True
                )
                log.debug(f'{self}: Bought CHI ({tx_hash})')
        deployer_balance = (
            chi_token.contract.functions.balanceOf(configs.ADDRESS)
            .call(block_identifier=configs.BLOCK)
        )
        amount_transfer = min(deployer_balance, CHI_CONTRACT_TOP_UP)
        log.info(f'Transfering {amount_transfer} CHI')
        tx_hash = tools.transaction.sign_and_send_contract_tx(
            chi_token.contract.functions.transfer,
            self.contract.address,
            amount_transfer,
            wait_finish_=True,
        )
        log.debug(f'{self}: Transfered CHI ({tx_hash})')


def get_deployer_balance_usd(web3: Web3) -> float:
    balance = web3.eth.get_balance(configs.ADDRESS) / 10 ** tools.price.get_native_token_decimals()
    return balance * tools.price.get_price_usd_native_token(web3)


def convert_amounts_native(amounts_convert: Iterable[TokenAmount], web3: Web3):
    for token_amount in amounts_convert:
        log.info(f'Converting {token_amount}')
        if token_amount.token == WRAPPED_CURRENCY_TOKEN:  # WBNB / WETH
            contract = web3.eth.contract(token_amount.token.address, abi=WETH_ABI)
            tx_hash = tools.transaction.sign_and_send_contract_tx(
                contract.functions.withdraw,
                token_amount.amount,
                wait_finish_=True
            )
        else:
            tx_hash = tools.exchange.exchange_1inch(
                web3,
                token_amount,
                max_slippage=MAX_SLIPPAGE,
                wait_finish=True
            )
        log.debug(f'Converted {token_amount} to native currency ({tx_hash})')


def convert_amounts_stable(
    amounts_convert: Iterable[TokenAmount],
    stable_reserve_token: Token,
    web3: Web3
):
    for token_amount in amounts_convert:
        log.info(f'Converting {token_amount}')
        tx_hash = tools.exchange.exchange_1inch(
            web3,
            token_amount,
            stable_reserve_token,
            max_slippage=MAX_SLIPPAGE,
            wait_finish=True
        )
        log.debug(f'Converted {token_amount} to {stable_reserve_token} ({tx_hash})')


def convert_amounts(tokens: Iterable[Token], stable_reserve_token: Token, web3: Web3):
    balances = get_address_balances_in_native_currency(configs.ADDRESS, tokens)
    amounts_convert = [
        token_amount
        for token_amount, native_amount in balances
        if native_amount > 0
    ]
    if (convert_to_stable := get_deployer_balance_usd(web3) > NATIVE_CURRENCY_USD_RESERVE):
        amounts_convert = [
            token_amount
            for token_amount in amounts_convert
            if token_amount.token != stable_reserve_token
        ]
    if not amounts_convert:
        log.info('No tokens to convert')
        return
    if convert_to_stable:
        log.info(f'Converting to {stable_reserve_token.symbol}')
        convert_amounts_stable(amounts_convert, stable_reserve_token, web3)
    else:
        log.info(f'Converting to {NATIVE_CURRENCY_SYMBOL}')
        convert_amounts_native(amounts_convert, web3)
    log.info('Finished converting tokens from deployer address')


def get_strategy(strategy_name: str, web3: Web3):
    strategy = importlib.import_module(f'strategies.{strategy_name}')
    dexes = PairManager.load_dex_protocols(strategy.ADDRESS_DIRECTORY, strategy.DEX_PROTOCOLS, web3)
    contract = tools.transaction.load_contract(strategy.CONTRACT_DATA_FILEPATH)
    return Strategy(contract, dexes, strategy_name)


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

        balance_stable = (
            stable_reserve_token.contract.functions.balanceOf(configs.ADDRESS)
            .call(block_identifier=configs.BLOCK)
        )
        balance_stable_units = balance_stable / 10 ** stable_reserve_token.decimals

        log.info(
            f'Account balance: {balance_native_units:.6f} {NATIVE_CURRENCY_SYMBOL}; '
            f'{balance_stable_units:.2f} {stable_reserve_token.symbol}'
        )
        time.sleep(RUN_INTERVAL)
