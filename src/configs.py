import os

# Logs
LOG_AWS = os.getenv('LOG_AWS') == 'True'

# Web3
RPC_REMOTE_URI = os.getenv('RPC_REMOTE_URI', 'wss://bsc-ws-node.nariox.org:443')
RPC_LOCAL_URI = os.getenv('RPC_LOCAL_URI', 'geth.ipc')
CHAIN_ID = int(os.environ['CHAIN_ID'])
POA_CHAIN = os.getenv('POA_CHAIN') == 'True'
MULTI_BROADCAST_TRANSACTIONS = os.getenv('MULTI_BROADCAST_TRANSACTIONS') == 'True'
USE_REMOTE_RCP_CONNECTION = os.getenv('USE_REMOTE_RCP_CONNECTION') == 'True'

# Wallet
PRIVATE_KEY = os.environ['PRIVATE_KEY']
ADDRESS = os.environ['ADDRESS']

# Connection params
CACHE_TTL = float(os.environ['CACHE_TTL'])
POLL_INTERVAL = float(os.environ['POLL_INTERVAL'])

# Arbitrage params
STRATEGY = os.getenv('STRATEGY', 'no_strategy')

# Debug / optimization
CACHE_STATS = os.getenv('CACHE_STATS') == 'True'
CACHE_LOG_LEVEL = os.getenv('CACHE_LOG_LEVEL', 'INFO')

# Gas
BASELINE_GAS_PRICE_PREMIUM = float(os.getenv('BASELINE_GAS_PRICE_PREMIUM', '1.0000000012'))
MIN_GAS_PRICE = int(os.getenv('MIN_GAS_PRICE', '5000000000'))

# Testing
BLOCK = 'latest'
STOP_RESERVE_UPDATE = False
