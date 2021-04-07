# flash

Arbitrage using flashloans

## Requirements
 - [docker](https://docs.docker.com/engine/install). If on linux, follow [post-install steps](https://docs.docker.com/engine/install/linux-postinstall/)
 - npm (to install truffle): `sudo apt install npm`
 - truffle: `sudo npm install -g truffle`
 - yarn (recommended to install javascript dependencies): `sudo npm install -g yarn`

---
## Project commands
 - Use `make` to see Makefile actions

---
## Current strategies
 1. **pancakeswap_ellipsis_3_pool_v2**: Trade Ellipsis' [3pool](https://ellipsis.finance/3pool) vs [pancakeswap](https://exchange.pancakeswap.finance/#/swap). Pancakeswap max_hops=2 to include WBNB liquidity pairs
