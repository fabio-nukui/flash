import json
import logging
import urllib.parse
from datetime import datetime
from typing import Iterable

import httpx
from web3 import Web3

import configs
from core import LiquidityPair, Token
from tools import w3
from tools.cache import ttl_cache

USD_PRICE_FEED_ADDRESSES = \
    json.load(open('addresses/chainlink_usd_price_feeds.json'))[str(configs.CHAIN_ID)]
CHAINLINK_PRICE_FEED_ABI = json.load(open('abis/ChainlinkPriceFeed.json'))
WRAPPED_CURRENCY_TOKENS_DATA = json.load(open('addresses/wrapped_currency_tokens.json'))

# These functions should not be used for too time-critical data, so ttl can be higher
USD_PRICE_CACHE_TTL = 360
GAS_PRICE_CACHE_TTL = 1800
USD_PRICE_DATA_STALE = 3600
TOKEN_SYNONYMS = {
    'BTCB': 'BTC',
    'WTCB': 'BTC',
    'WBNB': 'BNB',
    'WETH': 'ETH',
}

WEB3 = w3.get_web3()
log = logging.getLogger(__name__)


def _get_native_token_decimals():
    if configs.CHAIN_ID in (1, 56):
        return 18
    raise NotImplementedError


@ttl_cache(maxsize=1000, ttl=USD_PRICE_CACHE_TTL)
def _get_chainlink_data(asset_name: str, address: str, decimals: int, web3: Web3) -> float:
    contract = web3.eth.contract(address, abi=CHAINLINK_PRICE_FEED_ABI)
    (
        round_id, answer, started_at, updated_at, answered_in_round
    ) = contract.functions.latestRoundData().call()

    dt_updated_at = datetime.fromtimestamp(updated_at)
    seconds_since_last_update = (dt_updated_at - datetime.utcnow()).total_seconds()
    if seconds_since_last_update > USD_PRICE_DATA_STALE:
        log.warning(f'Price data for {asset_name} {seconds_since_last_update} seconds old')

    return answer / 10 ** decimals


def get_chainlink_price_usd(token_symbol: str, web3: Web3 = WEB3) -> float:
    token_symbol = TOKEN_SYNONYMS.get(token_symbol, token_symbol)

    address = USD_PRICE_FEED_ADDRESSES[token_symbol]['address']
    decimals = USD_PRICE_FEED_ADDRESSES[token_symbol]['decimals']

    return _get_chainlink_data(token_symbol, address, decimals, web3)


@ttl_cache(maxsize=100, ttl=GAS_PRICE_CACHE_TTL)
def get_gas_price(web3: Web3 = WEB3) -> int:
    return int(WEB3.eth.gas_price * configs.BASELINE_GAS_PRICE_PREMIUM)


def get_gas_cost_usd(gas: int, web3: Web3 = WEB3) -> float:
    if configs.CHAIN_ID == 56:
        asset_name = 'BNB'
    else:
        raise NotImplementedError
    address = USD_PRICE_FEED_ADDRESSES[asset_name]['address']
    decimals = USD_PRICE_FEED_ADDRESSES[asset_name]['decimals']

    gas_cost = float(Web3.fromWei(gas, 'ether')) * get_gas_price(web3)

    price_native_token_usd = _get_chainlink_data(asset_name, address, decimals, web3)
    return gas_cost * price_native_token_usd


async def get_prices_congecko(addresses: Iterable[str]) -> dict[str, float]:
    """Return Ethereum network token in USD from coingecko.com"""
    url = 'https://api.coingecko.com/api/v3/simple/token_price/ethereum'
    query_string = urllib.parse.urlencode({
        'contract_addresses': ','.join(addresses),
        'vs_currencies': 'USD',
    })
    res = httpx.get(f'{url}?{query_string}')
    res.raise_for_status()
    return {
        key: value['usd']
        for key, value in res.json().items()
    }


def get_price_usd(token: Token, pairs: list[LiquidityPair], web3: Web3 = WEB3) -> float:
    """Return token price in USD using chainlink and, if token not in chainlink, by comparing
    vs liquidity pair with largest liquidity and with chainlink usd price
    """
    try:
        return get_chainlink_price_usd(token.symbol, web3)
    except KeyError:
        pass
    liquidity_prices = []
    for pair in pairs:
        if token not in pair.tokens:
            continue
        if pair.tokens[0] == token:
            paired_token = pair.tokens[1]
            same_reserve, paired_reserve = pair.reserves
        else:
            paired_token = pair.tokens[0]
            paired_reserve, same_reserve = pair.reserves
        try:
            price_paired_token = get_chainlink_price_usd(paired_token.symbol, web3)
        except KeyError:
            continue
        liquidity = price_paired_token * paired_reserve.amount_in_units * 2
        price_token = price_paired_token * paired_reserve.amount / same_reserve.amount
        liquidity_prices.append((liquidity, price_token))
    if not liquidity_prices:
        raise Exception('Found no token with chainlink price linked to input token.')
    return max(liquidity_prices)[1]


def get_wrapped_currency_token(chain_id: int = configs.CHAIN_ID, web3: Web3 = WEB3) -> Token:
    try:
        data = WRAPPED_CURRENCY_TOKENS_DATA[str(chain_id)]
    except KeyError:
        raise Exception(f'No wrapped reference token for {chain_id=}')
    return Token(chain_id=chain_id, web3=web3, **data)
