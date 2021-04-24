import atexit
import os
import signal
import subprocess
from contextlib import contextmanager
from typing import Union

import configs
import tools


class HardhatForkProcess:
    DEFAULT_CMD = ['bash', 'scripts/hardhat-fork']

    def __init__(self, block: Union[int, str] = None):
        assert isinstance(block, int) or block in (None, 'latest')
        self.block = block

        self.proc: subprocess.Popen = None
        self.procgid: int = None
        atexit.register(self.stop)

    def _get_cmd(self) -> list[str]:
        if isinstance(self.block, int):
            return self.DEFAULT_CMD + [str(self.block)]
        return self.DEFAULT_CMD

    def start(self):
        self.proc = subprocess.Popen(
            self._get_cmd(),
            preexec_fn=os.setsid,
            text=True,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        self.procgid = os.getpgid(self.proc.pid)
        while True:  # Wait for process to be ready
            line = self.proc.stdout.readline()
            if 'Account #19' in line:
                break

    def stop(self):
        os.killpg(self.procgid, signal.SIGTERM)

    def restart_at_block(self, block: Union[int, str]):
        self.block = block
        self.stop()
        self.start()


@contextmanager
def stop_reserve_update():
    prev_stop_reserve_update = configs.STOP_RESERVE_UPDATE
    try:
        configs.STOP_RESERVE_UPDATE = True
        yield
    finally:
        configs.STOP_RESERVE_UPDATE = prev_stop_reserve_update


@contextmanager
def simulate_block(
    block: Union[int, str] = None,
    clear_all_caches: bool = True,
    fork_network: bool = False,
    hardhat_fork_process: HardhatForkProcess = None,
):
    if not fork_network:
        previous_block = configs.BLOCK
        block = 'latest' if block is None else block
        block = int(block) if not isinstance(block, str) else block  # Avoid errors with numpy.int
        tools.cache.clear_caches(clear_all=clear_all_caches)
        try:
            configs.BLOCK = block
            yield
        finally:
            configs.BLOCK = previous_block
            tools.cache.clear_caches(clear_all=clear_all_caches)
    elif hardhat_fork_process is None:
        try:
            hardhat_fork_process = HardhatForkProcess(block)
            hardhat_fork_process.start()
            tools.cache.clear_caches(clear_all=clear_all_caches)
            yield
        finally:
            hardhat_fork_process.stop()
            tools.cache.clear_caches(clear_all=clear_all_caches)
    else:
        previous_block = hardhat_fork_process.block
        try:
            hardhat_fork_process.restart_at_block(block)
            tools.cache.clear_caches(clear_all=clear_all_caches)
            yield
        finally:
            hardhat_fork_process.restart_at_block(previous_block)
            tools.cache.clear_caches(clear_all=clear_all_caches)
