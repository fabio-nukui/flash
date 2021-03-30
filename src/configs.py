import os

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_AWS = os.getenv('LOG_AWS') == 'True'

RCP_REMOTE_ENDPOINT = os.getenv('RCP_REMOTE_ENDPOINT', '')
RCP_LOCAL_ENDPOINT = os.getenv('RCP_LOCAL_ENDPOINT', 'http://localhost:8545')

PRIVATE_KEY = os.environ['PRIVATE_KEY']
ADDRESS = os.environ['ADDRESS']

CHAIN_ID = int(os.environ['CHAIN_ID'])
CACHE_TTL = float(os.environ['CACHE_TTL'])
POLL_INTERVAL = float(os.environ['POLL_INTERVAL'])

STRATEGY = os.environ['STRATEGY']
