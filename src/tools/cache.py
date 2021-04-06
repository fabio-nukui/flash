from threading import Lock
from typing import Callable, Union

from cachetools import TTLCache, cached

import configs

_cache_locks: list[tuple[TTLCache, Lock]] = []


class TTLCacheWithStats(TTLCache):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._n_hits = 0
        self._n_sets = 0
        self._n_hits_total = 0
        self._n_sets_total = 0

    def clear(self):
        super().clear()
        self._n_hits = 0
        self._n_sets = 0

    def __getitem__(self, key):
        hit = super().__getitem__(key)
        self._n_hits += 1
        self._n_hits_total += 1
        return hit

    def setdefault(self, k, v):
        self._n_sets += 1
        self._n_sets_total += 1
        return super().setdefault(k, v)


def _get_ttl_cache_lock(maxsize: int = 1, ttl: float = configs.CACHE_TTL) -> tuple[TTLCache, Lock]:
    """Return (TTLCacke, Lock) pairs to allow for safe cache clear"""
    lock = Lock()

    if configs.CACHE_STATS:
        cache = TTLCacheWithStats(maxsize, ttl)
    else:
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


def get_stats():
    if not configs.CACHE_STATS:
        raise Exception('Stats only available if configs.CACHE_STATS=True')
    return {
        'n_hits': sum(cache._n_hits for cache, _ in _cache_locks),
        'n_sets': sum(cache._n_sets for cache, _ in _cache_locks),
        'n_hits_total': sum(cache._n_hits_total for cache, _ in _cache_locks),
        'n_sets_total': sum(cache._n_hits_total for cache, _ in _cache_locks),
    }
