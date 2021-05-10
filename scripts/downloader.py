#!/usr/bin/env python3
import asyncio
import concurrent.futures
import os
import sys
import time
from random import random

import requests
from tqdm import tqdm

URL = 'https://binance-smart-chain-snapshot.s3.amazonaws.com/snap.tar.gz'
DOWNLOAD_DIR = sys.argv[1] if len(sys.argv) > 0 else '/mnt/nvme0'
OUTPUT = os.path.join(DOWNLOAD_DIR, 'snap.tar.gz')
DOWNLOAD_JIGGLE_TIME = 10
N_WORKERS = 60
BLOCK_SIZE_DISK_WRITE = 10_2400  # 100 KB
BLOCK_SIZE_DOWNLOAD = 500_000_000  # 500 MiB
N_TRIES = 3


async def get_size(url):
    response = requests.get(url, stream=True)
    size = int(response.headers['Content-Length'])
    return size


def download_range(url, start, end, output):
    if os.path.exists(output):
        print(f'Skipping {output}')
        return
    time.sleep(random() * DOWNLOAD_JIGGLE_TIME)
    print(f'Starting {output}')
    headers = {'Range': f'bytes={start}-{end}'}
    response = requests.get(url, stream=True, headers=headers)

    for _ in range(N_TRIES):
        try:
            with open(f'{output}_incomplete', 'wb') as f:
                for part in response.iter_content(BLOCK_SIZE_DISK_WRITE):
                    f.write(part)
        except Exception:
            pass
        else:
            os.rename(f'{output}_incomplete', output)
            break
        finally:
            if os.path.exists(f'{output}_incomplete'):
                os.remove(f'{output}_incomplete')
    else:
        raise Exception(f'Error when downloading {output}')
    print(f'Finished {output}')


async def download(executor, url, output, chunk_size=BLOCK_SIZE_DOWNLOAD):
    loop = asyncio.get_event_loop()

    file_size = await get_size(url)
    chunks = range(0, file_size, chunk_size)

    tasks = [
        loop.run_in_executor(
            executor,
            download_range,
            url,
            start,
            start + chunk_size - 1,
            f'{output}.part{i:04d}',
        )
        for i, start in enumerate(chunks)
    ]

    await asyncio.wait(tasks)

    print('Finished downloads, consolidating parts')
    with open(output, 'wb') as o:
        for i in tqdm(range(len(chunks))):
            chunk_path = f'{output}.part{i:04d}'

            with open(chunk_path, 'rb') as s:
                o.write(s.read())
            os.remove(chunk_path)
    print('Finished')


if __name__ == '__main__':
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=N_WORKERS)
    asyncio.run(download(executor, URL, OUTPUT))
