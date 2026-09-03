"""Process-wide parse cache keyed by path or synthetic id."""

import threading

# Values are source-specific tuples; callers own the shape.
_cache = {}
_cache_lock = threading.Lock()


def get(key):
    return _cache.get(key)


def set(key, value):
    _cache[key] = value


def delete(key):
    _cache.pop(key, None)


def lock():
    return _cache_lock
