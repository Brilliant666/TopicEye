from datetime import datetime
import time

from app.services.json_cache import get_cached_json, invalidate_json_cache, set_cached_json


def test_json_cache_hit_expire_and_prefix_invalidate():
    invalidate_json_cache()

    content = set_cached_json("perf:a", {"created_at": datetime(2026, 1, 2, 3, 4, 5), "value": "中文"})
    assert b"2026-01-02T03:04:05" in content
    assert "中文".encode("utf-8") in content

    cached = get_cached_json("perf:a", ttl_seconds=10)
    assert cached is not None
    cached_content, age_seconds = cached
    assert cached_content == content
    assert age_seconds >= 0

    assert get_cached_json("perf:a", ttl_seconds=0) is None

    set_cached_json("perf:a", {"value": 1})
    set_cached_json("other:a", {"value": 2})
    invalidate_json_cache("perf:")
    assert get_cached_json("perf:a", ttl_seconds=10) is None
    assert get_cached_json("other:a", ttl_seconds=10) is not None

    invalidate_json_cache()
    assert get_cached_json("other:a", ttl_seconds=10) is None


def test_json_cache_respects_short_ttl():
    invalidate_json_cache()
    set_cached_json("ttl:test", {"value": 1})
    time.sleep(0.002)
    assert get_cached_json("ttl:test", ttl_seconds=0.001) is None
