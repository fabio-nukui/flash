from threading import Lock
from typing import Callable, Union

from cachetools import TTLCache, cached

import configs

cache_locks = []


def get_ttl_cache_lock(maxsize: int = 1, ttl: float = configs.CACHE_TTL) -> tuple[TTLCache, Lock]:
    """Return (TTLCacke, Lock) pairs to allow for safe cache clear"""
    lock = Lock()
    cache = TTLCache(maxsize, ttl)

    cache_lock_pair = (cache, lock)
    cache_locks.append(cache_lock_pair)

    return cache_lock_pair


def ttl_cache(maxsize: Union[int, Callable] = None, ttl: Union[int, float] = None):
    """Decorator to wrap a function with a memoizing callable that saves
    up to `maxsize` results based on a Least Recently Used (LRU)
    algorithm with a per-item time-to-live (TTL) value.
    """
    if callable(maxsize):
        cache, lock = get_ttl_cache_lock()
        raise Exception
        return cached(cache, lock=lock)
    else:
        cache, lock = get_ttl_cache_lock(maxsize, ttl)
        return cached(cache, lock=lock)


def clear_caches():
    for cache, lock in cache_locks:
        with lock:
            cache.clear()
