import atexit
import logging
import signal
from threading import Lock
from typing import Callable

log = logging.getLogger(__name__)

_lock = Lock()
_is_shutting_down = False


def is_shutting_down() -> bool:
    with _lock:
        return _is_shutting_down


def set_shutting_down_flag(*args):
    log.info('Shutting down')
    global _is_shutting_down
    with _lock:
        _is_shutting_down = True


def register_exit_handle(func: Callable):
    atexit.register(func)
    signal.signal(signal.SIGINT, func)
    signal.signal(signal.SIGTERM, func)


register_exit_handle(set_shutting_down_flag)
