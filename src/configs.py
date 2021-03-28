import os

RCP_WSS_URL = os.environ['RCP_WSS_URL']
RCP_HTTPS_URL = os.environ['RCP_HTTPS_URL']

PRIVATE_KEY = os.environ['PRIVATE_KEY']
ADDRESS = os.environ['ADDRESS']

CHAIN_ID = int(os.environ['CHAIN_ID'])
CACHE_TTL = float(os.environ['CACHE_TTL'])
POLL_INTERVAL = float(os.environ['POLL_INTERVAL'])
