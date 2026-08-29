from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

_NANOSECONDS_PER_SECOND = 1_000_000_000
_CACHE: dict[str, tuple[int, bytes]] = {}


def get_cached_json(cache_key: str, *, ttl_seconds: float) -> tuple[bytes, float] | None:
    """Return raw cached JSON bytes and age (for fast-path API responses)."""
    cached = _CACHE.get(cache_key)
    if not cached:
        return None
    cached_at, content = cached
    age_seconds = (time.perf_counter_ns() - cached_at) / _NANOSECONDS_PER_SECOND
    if ttl_seconds <= 0 or age_seconds > ttl_seconds:
        _CACHE.pop(cache_key, None)
        return None
    return content, age_seconds


def get_cached_value(cache_key: str, *, ttl_seconds: float) -> tuple[Any, float] | None:
    """Return deserialized cached value and age (for in-process dict consumers)."""
    cached = _CACHE.get(cache_key)
    if not cached:
        return None
    cached_at, content = cached
    age_seconds = (time.perf_counter_ns() - cached_at) / _NANOSECONDS_PER_SECOND
    if ttl_seconds <= 0 or age_seconds > ttl_seconds:
        _CACHE.pop(cache_key, None)
        return None
    return json.loads(content), age_seconds


def set_cached_json(cache_key: str, payload: Any) -> bytes:
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default).encode("utf-8")
    # ``time.monotonic()`` is backed by GetTickCount64 on Windows and may only
    # advance every 15.6 ms.  Cache callers use millisecond TTLs in tests and
    # diagnostics, so retain the monotonic guarantee while using the
    # high-resolution counter exposed by ``perf_counter_ns``.
    _CACHE[cache_key] = (time.perf_counter_ns(), content)
    return content


def invalidate_json_cache(prefix: str | None = None) -> None:
    if prefix is None:
        _CACHE.clear()
        return
    for key in list(_CACHE):
        if key.startswith(prefix):
            _CACHE.pop(key, None)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return str(value)
