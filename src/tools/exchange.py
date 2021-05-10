import json
import logging
from typing import Union

from web3 import Account, Web3

import configs
from core import Token, TokenAmount
from tools import http, price, transaction

log = logging.getLogger(__name__)

_1INCH_API_URL = f'https://api.1inch.exchange/v3.0/{configs.CHAIN_ID}'
TIMEOUT_REQUESTS = 10

# Stand-in for ETH or BNB swaps in 1inch
_1INCH_CURRENCY_ADDRESS = '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
DEFAULT_MAX_SLIPPAGE = 0.4  # 0.4% maximum splippage
with open('addresses/dex/_1inch_v3/_1inch_v3.json') as f:
    _1INCH_ROUTER_ADDRESS = json.load(f)[str(configs.CHAIN_ID)]['router']


def get_quote_1inch(
    amountIn: Union[int, TokenAmount],
    tokenOut: Token = None,
    gas_price: int = None,
) -> int:
    token_out_address = tokenOut.address if tokenOut is not None else _1INCH_CURRENCY_ADDRESS
    gas_price = price.get_gas_price() if gas_price is None else gas_price
    if isinstance(amountIn, TokenAmount):
        from_token_address = amountIn.token.address
        from_token_amount = amountIn.amount
    else:
        from_token_address = _1INCH_CURRENCY_ADDRESS
        from_token_amount = amountIn
    query_params = {
        'fromTokenAddress': from_token_address,
        'toTokenAddress': token_out_address,
        'amount': from_token_amount,
        'gasPrice': gas_price,
    }
    print(f'{_1INCH_API_URL}/quote', query_params)
    res = http.get(f'{_1INCH_API_URL}/quote', params=query_params, timeout=TIMEOUT_REQUESTS)
    amount = int(res.json()['toTokenAmount'])
    return amount


def exchange_1inch(
    web3: Web3,
    amountIn: Union[int, TokenAmount],
    tokenOut: Token = None,
    max_slippage: float = DEFAULT_MAX_SLIPPAGE,
    gas_price: int = None,
    wait_finish: bool = False,
    max_blocks_wait_: int = None,
    account: Account = None,
):
    token_out_address = tokenOut.address if tokenOut is not None else _1INCH_CURRENCY_ADDRESS
    gas_price = price.get_gas_price() if gas_price is None else gas_price
    address = configs.ADDRESS if account is None else account.address
    if isinstance(amountIn, TokenAmount):
        from_token_address = amountIn.token.address
        from_token_amount = amountIn.amount
        allowance = (
            amountIn.token.contract.functions.allowance(address, _1INCH_ROUTER_ADDRESS)
            .call(block_identifier=configs.BLOCK)
        )
        if allowance < from_token_amount:
            tx_hash = transaction.sign_and_send_contract_tx(
                amountIn.token.contract.functions.approve,
                _1INCH_ROUTER_ADDRESS,
                amountIn.amount,
                wait_finish_=True,
                account=account,
            )
            log.debug(f'Added {amountIn} allowance to 1inch ({tx_hash})')
    else:
        from_token_address = _1INCH_CURRENCY_ADDRESS
        from_token_amount = amountIn
    query_params = {
        'fromTokenAddress': from_token_address,
        'toTokenAddress': token_out_address,
        'amount': from_token_amount,
        'fromAddress': address,
        'slippage': max_slippage,
        'gasPrice': gas_price,
        'allowPartialFill': True,
    }
    res = http.get(
        f'{_1INCH_API_URL}/swap',
        n_tries=6,
        params=query_params,
        timeout=TIMEOUT_REQUESTS
    )
    tx = res.json()['tx']
    tx['gas'] = round(tx['gas'] * 1.25)
    tx['value'] = int(tx['value'])
    tx['gasPrice'] = int(tx['gasPrice'])
    tx['to'] = web3.toChecksumAddress(tx['to'])

    return transaction.sign_and_send_tx(tx, web3, wait_finish, max_blocks_wait_, account=account)
