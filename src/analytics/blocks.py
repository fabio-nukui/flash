import pandas as pd
from web3 import Web3

import tools

WEB3 = tools.w3.get_web3()


def get_receipts(block_number: int, web3: Web3 = WEB3) -> pd.DataFrame:
    data = [
        web3.eth.getTransactionReceipt(tx)
        for tx in web3.eth.get_block(block_number).transactions
    ]
    return pd.DataFrame(data)


def get_gas_data(block_number: int, web3: Web3 = WEB3) -> pd.DataFrame:
    data = [
        {
            'tx': tx.hex(),
            'price_gwei': web3.eth.getTransaction(tx).gasPrice / 10**9,
            'gas': web3.eth.getTransactionReceipt(tx).gasUsed
        }
        for tx in web3.eth.get_block(block_number).transactions
    ]
    return pd.DataFrame(data)
