import os

# Logs
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_AWS = os.getenv('LOG_AWS') == 'True'

# Web3
RCP_REMOTE_URI = os.getenv('RCP_REMOTE_URI', 'wss://bsc-ws-node.nariox.org:443')
RCP_LOCAL_URI = os.getenv('RCP_LOCAL_URI', 'geth.ipc')
CHAIN_ID = int(os.environ['CHAIN_ID'])
POA_CHAIN = os.getenv('POA_CHAIN') == 'True'

# Wallet
PRIVATE_KEY = os.environ['PRIVATE_KEY']
ADDRESS = os.environ['ADDRESS']

# Connection params
CACHE_TTL = float(os.environ['CACHE_TTL'])
POLL_INTERVAL = float(os.environ['POLL_INTERVAL'])

# Arbitrage params
STRATEGY = os.getenv('STRATEGY', 'no_strategy')
