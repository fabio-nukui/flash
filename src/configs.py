import os

RCP_ENDPOINT = os.getenv('RCP_ENDPOINT', 'http://localhost:8545')

PRIVATE_KEY = os.environ['PRIVATE_KEY']
ADDRESS = os.environ['ADDRESS']

CHAIN_ID = int(os.environ['CHAIN_ID'])
CACHE_TTL = float(os.environ['CACHE_TTL'])
POLL_INTERVAL = float(os.environ['POLL_INTERVAL'])

STRATEGY = os.environ['STRATEGY']
