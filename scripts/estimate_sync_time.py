import pathlib
import re
import time
from datetime import datetime

from web3.middleware import geth_poa_middleware
from web3 import Web3, HTTPProvider


POOL_INTERVAL = 1
PAT = re.compile(r'^t=(?P<t>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).+msg="Imported new chain segment".+\bnumber=(?P<n>\d+)\b')  # noqa: E501
N_LINES_BUFFER = 100

SECONDS_PER_BLOCK = 3
RCP_ENDPOINT = 'https://bsc-dataseed.binance.org'

DIR_PATH = pathlib.Path(__file__).parent / 'node'
PREFIX = 'bsc.log.'


class Logs:
    def __init__(self):
        self.log_files = sorted(self.get_files())
        self.lines = [
            line
            for file in self.log_files[:-1]
            for line in open(file).readlines()
        ]
        self.file = open(self.log_files[-1])

    def get_files(self):
        return (
            f for f in DIR_PATH.iterdir()
            if f.is_file() and not f.is_symlink() and f.name.startswith(PREFIX)
        )

    def update_newer_file(self):
        newest_file = max(self.get_files())
        if str(newest_file) == self.file.name:
            return
        self.file.close()
        self.log_files.append(self.file.name)
        self.file = open(newest_file)

    def iterlines(self):
        for line in self.lines:
            yield line
        self.lines = []
        while True:
            where = self.file.tell()
            line = self.file.readline()
            if line:
                yield line
                self.update_newer_file()
            else:
                time.sleep(POOL_INTERVAL)
                self.file.seek(where)

    def iterdata(self):
        for line in self.iterlines():
            match = PAT.search(line)
            if not match:
                continue
            d = match.groupdict()
            yield {
                't': datetime.fromisoformat(d['t']),
                'n': int(d['n'])
            }


class Blocks:
    def __init__(self):
        self.blocks = []

    def load_new_block(self, block):
        self.blocks.append(block)
        self.blocks = self.blocks[-100:]
        self.web3 = Web3(HTTPProvider(RCP_ENDPOINT), [geth_poa_middleware])

    @property
    def oldest_processed_block(self):
        return self.blocks[0]

    @property
    def last_processed_block(self):
        return self.blocks[-1]

    def get_blocks_per_second(self) -> float:
        if self.oldest_processed_block == self.last_processed_block:
            return float('nan')
        delta_time = self.oldest_processed_block['t'] - self.last_processed_block['t']
        delta_seconds = delta_time.total_seconds()
        delta_blocks = self.oldest_processed_block['n'] - self.last_processed_block['n']
        return delta_blocks / delta_seconds

    @property
    def latest_block(self):
        return {
            't': datetime.now(),
            'n': self.web3.eth.block_number
        }

    @property
    def blocks_remaining(self):
        return self.latest_block['n'] - self.last_processed_block['n']

    def get_hours_remaining(self):
        blocks_per_second = self.get_blocks_per_second()
        if blocks_per_second <= 1 / SECONDS_PER_BLOCK:
            return float('inf')
        return self.blocks_remaining / (blocks_per_second - 1 / SECONDS_PER_BLOCK) / 3600


def main():
    logs = Logs()
    blocks = Blocks()
    for d in logs.iterdata():
        blocks.load_new_block(d)
        time_left = blocks.get_hours_remaining()
        log = (
            f'{blocks.last_processed_block["t"].isoformat()}: '
            f'blocks left: {blocks.blocks_remaining}; '
            f'blocks/s: {blocks.get_blocks_per_second():,.2f}; '
            f'time left: {time_left:,.2f}; '
        )
        print(log)


if __name__ == '__main__':
    main()
