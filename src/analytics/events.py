from web3 import Web3

from . import blocks


def get_mappings_from_abi(abi: dict) -> list[dict]:
    return [
        {
            'name': e['name'],
            'data': [{'name': d['name'], 'type': d['type']} for d in e['inputs']],
            'hash': Web3.sha3(text=f"{e['name']}({','.join(i['type'] for i in e['inputs'])})").hex()
        }
        for e in abi
        if e['type'].lower() == 'event'
    ]


def process_block_events(receipts: list[dict], abis: list[dict]) -> list[dict]:
    receipts = blocks.get_receipts(block_number)
    event_mappings = [get_mappings_from_abi(a) for a in abis]

