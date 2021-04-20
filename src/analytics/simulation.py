import os
import signal
import subprocess
from contextlib import contextmanager
from typing import Union

import configs
import tools


@contextmanager
def simulate_block(
    block: Union[int, str] = None,
    stop_reserve_update: bool = False,
    clear_all_caches: bool = True,
    fork_network: bool = False,
):
    prev_stop_reserve_update = configs.STOP_RESERVE_UPDATE
    if fork_network:
        try:
            if stop_reserve_update:
                configs.STOP_RESERVE_UPDATE = True
            cmd = ['bash', 'scripts/hardhat-fork']
            if block is not None:
                cmd.append(str(block))
            proc = subprocess.Popen(cmd, preexec_fn=os.setsid)
            yield proc
        finally:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            configs.STOP_RESERVE_UPDATE = prev_stop_reserve_update
    else:
        previous_block = configs.BLOCK
        block = 'latest' if block is None else block
        if not isinstance(block, str):
            block_number = int(block)
        configs.BLOCK = block_number
        tools.cache.clear_caches(clear_all=clear_all_caches)
        try:
            if stop_reserve_update:
                configs.STOP_RESERVE_UPDATE = True
            yield
        finally:
            configs.BLOCK = previous_block
            configs.STOP_RESERVE_UPDATE = prev_stop_reserve_update
