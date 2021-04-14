import json
import urllib.parse

import httpx
from web3 import Web3

import configs
from core import Token, TokenAmount
from tools import contracts, price

_1INCH_API_URL = f'https://api.1inch.exchange/v3.0/{configs.CHAIN_ID}'

# Stand-in for ETH or BNB swaps in 1inch
_1INCH_CURRENCY_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
DEFAULT_MAX_SLIPPAGE = 0.4  # 0.4% maximum splippage
with open('addresses/dex/_1inch_v3/_1inch_v3.json') as f:
    _1INCH_ROUTER_ADDRESS = json.load(f)[str(configs.CHAIN_ID)]['router']


def get_quote_1inch(
    amountIn: TokenAmount,
    tokenOut: Token = None,
    gas_price: int = None
) -> int:
    token_out_address = tokenOut.address if tokenOut is not None else _1INCH_CURRENCY_ADDRESS
    gas_price = price.get_gas_price() if gas_price is None else gas_price
    query_string = urllib.parse.urlencode({
        'fromTokenAddress': amountIn.token.address,
        'toTokenAddress': token_out_address,
        'amount': amountIn.amount,
        'gasPrice': gas_price,
    })
    res = httpx.get(f'{_1INCH_API_URL}/quote?{query_string}')
    res.raise_for_status()
    amount = int(res.json()['toTokenAmount'])
    return amount


def exchange_1inch(
    web3: Web3,
    amountIn: TokenAmount,
    tokenOut: Token = None,
    max_slippage: float = DEFAULT_MAX_SLIPPAGE,
    gas_price: int = None,
):
    token_out_address = tokenOut.address if tokenOut is not None else _1INCH_CURRENCY_ADDRESS
    gas_price = price.get_gas_price() if gas_price is None else gas_price
    contracts.sign_and_send_contract_transaction(
        amountIn.token.contract.functions.approve,
        _1INCH_ROUTER_ADDRESS,
        amountIn.amount,
        wait_finish_=True
    )
    query_string = urllib.parse.urlencode({
        'fromTokenAddress': amountIn.token.address,
        'toTokenAddress': token_out_address,
        'amount': amountIn.amount,
        'fromAddress': configs.ADDRESS,
        'slippage': max_slippage,
        'gasPrice': gas_price,
        'allowPartialFill': True,
    })
    res = httpx.get(f'{_1INCH_API_URL}/swap?{query_string}')
    res.raise_for_status()

    tx = res.json()['tx']
    tx['gas'] = int(tx['gas'] * 1.25)
    tx['value'] = int(tx['value'])
    tx['gasPrice'] = int(tx['gasPrice'])
    tx['to'] = web3.toChecksumAddress(tx['to'])

    return contracts.sign_and_send_transaction(tx, web3)
