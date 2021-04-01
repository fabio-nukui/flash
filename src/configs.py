import os

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_AWS = os.getenv('LOG_AWS') == 'True'

RCP_REMOTE_URI = os.getenv('RCP_REMOTE_URI', 'wss://dummy.com')
RCP_LOCAL_URI = os.getenv('RCP_LOCAL_URI', 'node/geth.ipc')

PRIVATE_KEY = os.environ['PRIVATE_KEY']
ADDRESS = os.environ['ADDRESS']

CHAIN_ID = int(os.environ['CHAIN_ID'])
POA_CHAIN = os.getenv('POA_CHAIN') == 'True'
CACHE_TTL = float(os.environ['CACHE_TTL'])
POLL_INTERVAL = float(os.environ['POLL_INTERVAL'])

STRATEGY = os.environ['STRATEGY']
