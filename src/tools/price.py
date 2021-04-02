import json
import urllib.parse
from datetime import datetime
from typing import Iterable

import httpx
from web3 import Web3

import configs
from tools.cache import ttl_cache
from tools.logger import log

USD_PRICE_FEED_ADDRESSES = \
    json.load(open('addresses/chainlink_usd_price_feeds.json'))[str(configs.CHAIN_ID)]
CHAINLINK_PRICE_FEED_ABI = json.load(open('abis/ChainlinkPriceFeed.json'))

# This function should not be used for too time-critical data, so ttl can be higher
USD_PRICE_CACHE_TTL = 60
USD_PRICE_DATA_STALE = 300


def _get_native_token_decimals():
    if configs.CHAIN_ID in (1, 56):
        return 18
    raise NotImplementedError


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


@ttl_cache(maxsize=100, ttl=USD_PRICE_CACHE_TTL)
def get_chainlink_price_usd(token_symbol: str, web3: Web3) -> float:
    if configs.CHAIN_ID == 56 and token_symbol == 'WBNB':
        token_symbol = 'BNB'

    address = USD_PRICE_FEED_ADDRESSES[token_symbol]['address']
    decimals = USD_PRICE_FEED_ADDRESSES[token_symbol]['decimals']

    return _get_chainlink_data(token_symbol, address, decimals, web3)


@ttl_cache(maxsize=100, ttl=USD_PRICE_CACHE_TTL)
def get_gas_cost_usd(gas: int, web3: Web3) -> float:
    if configs.CHAIN_ID == 56:
        asset_name = 'BNB'
    else:
        raise NotImplementedError
    address = USD_PRICE_FEED_ADDRESSES[asset_name]['address']
    decimals = USD_PRICE_FEED_ADDRESSES[asset_name]['decimals']

    gas_cost = float(web3.fromWei(gas, 'ether') * web3.eth.gas_price)

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
