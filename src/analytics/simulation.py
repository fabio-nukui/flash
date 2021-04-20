import atexit
import os
import signal
import subprocess
from contextlib import contextmanager
from typing import Union

import configs
import tools


class HardhatForkProcess:
    def __init__(self, block: Union[int, str] = None):
        self.cmd = ['bash', 'scripts/hardhat-fork']
        if isinstance(block, int):
            self.cmd.append(str(block))
        else:
            assert block is None or block == 'latest'
        self.proc: subprocess.Popen = None
        self.procgid: int = None
        atexit.register(self.stop)

    def start(self):
        self.proc = subprocess.Popen(self.cmd, preexec_fn=os.setsid)
        self.procgid = os.getpgid(self.proc.pid)

    def stop(self):
        os.killpg(self.procgid, signal.SIGTERM)


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
            hardhat_fork = HardhatForkProcess(block)
            hardhat_fork.start()
            yield
        finally:
            configs.STOP_RESERVE_UPDATE = prev_stop_reserve_update
            hardhat_fork.stop()
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
