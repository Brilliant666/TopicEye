"""Bounded, process-local reuse of validated public read projections.

All entries share one 20-second epoch, so nested consumers cannot compound
their TTLs. No disk state, user identity, model result or budget is created.
Cross-process atomic writes are noticed by cheap path signatures where known;
the epoch also bounds legacy/in-place changes to at most 20 seconds.
"""

from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock, get_ident
from time import monotonic

MAX_ENTRIES = 96
TTL_SECONDS = 20
_entries = OrderedDict()
_inflight = {}
_lock = RLock()
_generation = 0


class _Flight:
    """One build shared by callers of the same cache key and epoch."""

    def __init__(self, generation: int) -> None:
        self.generation = generation
        self.owner = get_ident()
        self.event = Event()
        self.value = None
        self.error: BaseException | None = None


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
    """Reuse one build per key and epoch without serializing unrelated reads."""
    epoch = int(monotonic() // TTL_SECONDS)
    cache_key = (epoch, *key)

    with _lock:
        if cache_key in _entries:
            _entries.move_to_end(cache_key)
            value = _entries[cache_key]
            flight = None
            build_here = False
        else:
            flight_key = (_generation, cache_key)
            flight = _inflight.get(flight_key)
            if flight is None:
                flight = _Flight(_generation)
                _inflight[flight_key] = flight
                build_here = True
            elif flight.owner == get_ident():
                raise RuntimeError("recursive cache build for the same key")
            else:
                build_here = False

    if build_here:
        try:
            value = build()
        except BaseException as exc:
            with _lock:
                if _inflight.get(flight_key) is flight:
                    del _inflight[flight_key]
                flight.error = exc
                flight.event.set()
            raise

        with _lock:
            if _inflight.get(flight_key) is flight:
                del _inflight[flight_key]
            if flight.generation == _generation:
                _entries[cache_key] = value
                _entries.move_to_end(cache_key)
                while len(_entries) > MAX_ENTRIES:
                    _entries.popitem(last=False)
            flight.value = value
            flight.event.set()
    elif flight is not None:
        flight.event.wait()
        if flight.error is not None:
            raise flight.error
        value = flight.value

    return deepcopy(select(value) if select else value)


def clear() -> None:
    global _generation

    with _lock:
        _entries.clear()
        _inflight.clear()
        _generation += 1
