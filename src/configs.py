import os

RCP_WSS_ENDPOINT = os.getenv('RCP_WSS_ENDPOINT', 'localhost')
RCP_HTTPS_ENDPOINT = os.getenv('RCP_HTTPS_ENDPOINT', 'localhost')

PRIVATE_KEY = os.environ['PRIVATE_KEY']
ADDRESS = os.environ['ADDRESS']

CHAIN_ID = int(os.environ['CHAIN_ID'])
CACHE_TTL = float(os.environ['CACHE_TTL'])
POLL_INTERVAL = float(os.environ['POLL_INTERVAL'])
