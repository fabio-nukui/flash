import atexit
import logging
import signal
from threading import Lock
from typing import Callable

log = logging.getLogger(__name__)

_lock = Lock()
_is_shutting_down = False
_handlers: list[Callable] = []


def is_shutting_down() -> bool:
    with _lock:
        return _is_shutting_down


def set_shutting_down_flag(*args):
    log.info('Shutting down')
    global _is_shutting_down
    with _lock:
        _is_shutting_down = True


def _run_exit_handlers(*args):
    for handler in _handlers:
        handler()


def register_exit_handle(func: Callable):
    atexit.register(func)
    _handlers.append(func)


register_exit_handle(set_shutting_down_flag)
signal.signal(signal.SIGINT, _run_exit_handlers)
signal.signal(signal.SIGTERM, _run_exit_handlers)
