import httpx

import urllib.parse
from typing import Iterable


async def get_prices(addresses: Iterable[str]) -> dict[str, float]:
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
