import pandas as pd

import tools

WEB3 = tools.w3.get_web3()


def get_receipts(block_number: int) -> pd.DataFrame:
    data = [
        WEB3.eth.getTransactionReceipt(tx)
        for tx in WEB3.eth.get_block(block_number).transactions
    ]
    return pd.DataFrame(data)


def get_gas_data(block_number: int) -> pd.DataFrame:
    data = [
        {
            'tx': tx.hex(),
            'price_gwei': WEB3.eth.getTransaction(tx).gasPrice / 10**9,
            'gas': WEB3.eth.getTransactionReceipt(tx).gasUsed
        }
        for tx in WEB3.eth.get_block(block_number).transactions
    ]
    return pd.DataFrame(data)
