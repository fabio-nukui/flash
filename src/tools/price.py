import json
import logging
import urllib.parse
from datetime import datetime
from typing import Iterable, Union

from web3 import Web3

import configs
from core import LiquidityPair, Token
from exceptions import InsufficientLiquidity
from tools import http, w3
from tools.cache import ttl_cache

CHAINLINK_PRICE_FEED_ABI = json.load(open('abis/ChainlinkPriceFeed.json'))
WRAPPED_CURRENCY_TOKEN = Token(
    chain_id=configs.CHAIN_ID,
    **json.load(open('addresses/wrapped_currency_tokens.json'))[str(configs.CHAIN_ID)]
)

_USD_PRICE_FEED_ADDRESSES = \
    json.load(open('addresses/chainlink_usd_price_feeds.json'))[str(configs.CHAIN_ID)]
PRICE_FEEDS = {
    Token(chain_id=configs.CHAIN_ID, **data.pop('token')): data
    for data in _USD_PRICE_FEED_ADDRESSES['tokens']
}
PRICE_FEEDS.update({
    _USD_PRICE_FEED_ADDRESSES['native_currency'].pop('symbol'):
    _USD_PRICE_FEED_ADDRESSES['native_currency']
})
PRICE_FEEDS.update({WRAPPED_CURRENCY_TOKEN: _USD_PRICE_FEED_ADDRESSES['native_currency']})


# These functions should not be used for too time-critical data, so ttl can be higher
USD_PRICE_CACHE_TTL = 60
GAS_PRICE_CACHE_TTL = 300
USD_PRICE_DATA_STALE = 3600

WEB3 = w3.get_web3()
log = logging.getLogger(__name__)


def get_native_token_decimals():
    if configs.CHAIN_ID in (1, 56):
        return 18
    raise NotImplementedError


def get_native_token_symbol():
    if configs.CHAIN_ID == 1:
        return 'ETH'
    if configs.CHAIN_ID == 56:
        return 'BNB'


@ttl_cache(maxsize=1000, ttl=USD_PRICE_CACHE_TTL)
def _get_chainlink_data(asset: Union[str, Token], address: str, decimals: int, web3: Web3) -> float:
    contract = web3.eth.contract(address, abi=CHAINLINK_PRICE_FEED_ABI)
    (
        round_id, answer, started_at, updated_at, answered_in_round
    ) = contract.functions.latestRoundData().call(block_identifier=configs.BLOCK)

    dt_updated_at = datetime.fromtimestamp(updated_at)
    seconds_since_last_update = (dt_updated_at - datetime.utcnow()).total_seconds()
    if seconds_since_last_update > USD_PRICE_DATA_STALE:
        log.warning(f'Price data for {asset} {seconds_since_last_update} seconds old')

    return answer / 10 ** decimals


def get_chainlink_price_usd(asset: Union[str, Token], web3: Web3 = WEB3) -> float:
    address = PRICE_FEEDS[asset]['address']
    decimals = PRICE_FEEDS[asset]['decimals']

    return _get_chainlink_data(asset, address, decimals, web3)


@ttl_cache(maxsize=100, ttl=GAS_PRICE_CACHE_TTL)
def get_gas_price(web3: Web3 = WEB3) -> int:
    return int(WEB3.eth.gas_price * configs.BASELINE_GAS_PRICE_PREMIUM)


def get_gas_cost_native_tokens(gas: int, web3: Web3 = WEB3) -> float:
    return float(Web3.fromWei(gas, 'ether')) * get_gas_price(web3)


def get_gas_cost_usd(gas: int, web3: Web3 = WEB3) -> float:
    asset_name = get_native_token_symbol()
    address = PRICE_FEEDS[asset_name]['address']
    decimals = PRICE_FEEDS[asset_name]['decimals']

    gas_cost = get_gas_cost_native_tokens(gas, web3)

    price_native_token_usd = _get_chainlink_data(asset_name, address, decimals, web3)
    return gas_cost * price_native_token_usd


async def get_prices_coingecko(addresses: Iterable[str]) -> dict[str, float]:
    """Return Ethereum network token in USD from coingecko.com"""
    url = 'https://api.coingecko.com/api/v3/simple/token_price/ethereum'
    query_string = urllib.parse.urlencode({
        'contract_addresses': ','.join(addresses),
        'vs_currencies': 'USD',
    })
    res = http.get(f'{url}?{query_string}')
    return {
        key: value['usd']
        for key, value in res.json().items()
    }


def get_price_usd_native_token(web3: Web3) -> float:
    symbol = get_native_token_symbol()
    return get_chainlink_price_usd(symbol, web3)


def get_price_usd(token: Token, pools: list[LiquidityPair], web3: Web3 = WEB3) -> float:
    """Return token price in USD using chainlink and, if token not in chainlink, by comparing
    vs liquidity pair with largest liquidity and with chainlink usd price
    """
    try:
        return get_chainlink_price_usd(token, web3)
    except KeyError:
        pass
    liquidity_prices = []
    for pool in pools:
        if token not in pool.tokens:
            continue
        if pool.tokens[0] == token:
            paired_token = pool.tokens[1]
            same_reserve, paired_reserve = pool.reserves
        else:
            paired_token = pool.tokens[0]
            paired_reserve, same_reserve = pool.reserves
        try:
            price_paired_token = get_chainlink_price_usd(paired_token, web3)
        except KeyError:
            continue
        liquidity = price_paired_token * paired_reserve.amount_in_units * 2
        price_token = price_paired_token * paired_reserve.amount / same_reserve.amount
        liquidity_prices.append((liquidity, price_token))
    if not liquidity_prices:
        raise InsufficientLiquidity('Found no token with chainlink price linked to input token.')
    return max(liquidity_prices)[1]


def get_wrapped_currency_token() -> Token:
    return WRAPPED_CURRENCY_TOKEN
