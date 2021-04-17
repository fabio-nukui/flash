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


def get_transactions(block_number: int, web3: Web3 = WEB3) -> pd.DataFrame:
    df_receipts = get_receipts(block_number, web3)
    df_transactions = pd.DataFrame([
        web3.eth.get_transaction(tx)
        for tx in web3.eth.get_block(block_number).transactions
    ])
    assert df_receipts.index.equals(df_transactions.index)
    assert df_receipts['transactionIndex'].equals(df_transactions['transactionIndex'])
    receipts_columns = [
        'blockNumber',
        'gasUsed',
        'cumulativeGasUsed',
        'from',
        'logs',
        'status',
        'to',
        'transactionHash',
        'transactionIndex',
    ]
    transactions_columns = [
        'gas',
        'gasPrice',
        'input',
        'nonce',
        'value'
    ]
    return pd.concat([df_receipts[receipts_columns], df_transactions[transactions_columns]], axis=1)


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
