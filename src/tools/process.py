import atexit
import logging
import signal
from typing import Callable

log = logging.getLogger(__name__)

is_shutting_down = False


def set_shutting_down_flag():
    log.info('Shutting down')
    global is_shutting_down
    is_shutting_down = True


def register_exit_handle(func: Callable):
    atexit.register(func)
    signal.signal(signal.SIGINT, func)
    signal.signal(signal.SIGTERM, func)


register_exit_handle(set_shutting_down_flag)
