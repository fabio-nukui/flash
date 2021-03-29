from threading import Lock
from typing import Callable, Union

from cachetools import TTLCache, cached

import configs

_cache_locks = []


def _get_ttl_cache_lock(maxsize: int = 1, ttl: float = configs.CACHE_TTL) -> tuple[TTLCache, Lock]:
    """Return (TTLCacke, Lock) pairs to allow for safe cache clear"""
    lock = Lock()
    cache = TTLCache(maxsize, ttl)

    cache_lock_pair = (cache, lock)
    _cache_locks.append(cache_lock_pair)

    return cache_lock_pair


def ttl_cache(maxsize: Union[int, Callable] = 1, ttl: Union[int, float] = configs.CACHE_TTL):
    """TTL cache decorator with safe global clear function"""
    if callable(maxsize):
        # ttl_cache was applied directly
        func = maxsize
        cache, lock = _get_ttl_cache_lock()

        return cached(cache, lock=lock)(func)
    else:
        cache, lock = _get_ttl_cache_lock(maxsize, ttl)
        return cached(cache, lock=lock)


def clear_caches():
    for cache, lock in _cache_locks:
        with lock:
            cache.clear()
