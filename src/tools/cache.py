from typing import Callable, Union

from cachetools import TTLCache, cached

import configs

_caches: list[TTLCache] = []


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


def _get_ttl_cache(maxsize: int = 1, ttl: float = configs.CACHE_TTL) -> TTLCache:
    if configs.CACHE_STATS:
        cache = TTLCacheWithStats(maxsize, ttl)
    else:
        cache = TTLCache(maxsize, ttl)

    _caches.append(cache)
    return cache


def ttl_cache(maxsize: Union[int, Callable] = 100, ttl: Union[int, float] = configs.CACHE_TTL):
    """TTL cache decorator with safe global clear function"""
    if callable(maxsize):
        # ttl_cache was applied directly
        func = maxsize
        cache = _get_ttl_cache()

        return cached(cache)(func)
    else:
        cache = _get_ttl_cache(maxsize, ttl)
        return cached(cache)


def clear_caches():
    for cache in _caches:
        cache.clear()


def get_stats():
    if not configs.CACHE_STATS:
        raise Exception('Stats only available if configs.CACHE_STATS=True')
    return {
        'n_hits': sum(cache._n_hits for cache in _caches),
        'n_sets': sum(cache._n_sets for cache in _caches),
        'n_hits_total': sum(cache._n_hits_total for cache in _caches),
        'n_sets_total': sum(cache._n_hits_total for cache in _caches),
    }
