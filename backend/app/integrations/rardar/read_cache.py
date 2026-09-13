"""Bounded, process-local reuse of validated public read projections.

All entries share one 20-second epoch, so nested consumers cannot compound
their TTLs. No disk state, user identity, model result or budget is created.
Cross-process atomic writes are noticed by cheap path signatures where known;
the epoch also bounds legacy/in-place changes to at most 20 seconds.
"""

from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import monotonic

MAX_ENTRIES = 96
TTL_SECONDS = 20
_entries = OrderedDict()
_lock = RLock()


def signature(*paths: Path) -> tuple:
    result = []
    for path in paths:
        try:
            value = path.stat()
            result.append((str(path), value.st_mtime_ns, value.st_size))
        except FileNotFoundError:
            result.append((str(path), None))
    return tuple(result)


def cached(key: tuple, build, *, select=None):
    """Single-flight under a bounded lock; failed builds are never cached."""
    epoch = int(monotonic() // TTL_SECONDS)
    cache_key = (epoch, *key)
    with _lock:
        if cache_key not in _entries:
            value = build()
            _entries[cache_key] = value
            while len(_entries) > MAX_ENTRIES:
                _entries.popitem(last=False)
        _entries.move_to_end(cache_key)
        value = _entries[cache_key]
        return deepcopy(select(value) if select else value)


def clear() -> None:
    with _lock:
        _entries.clear()
