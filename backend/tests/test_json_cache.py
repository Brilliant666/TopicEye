from datetime import datetime
import time

from app.services.content_list_cache import ContentListCacheParams, invalidate_content_list_cache
from app.services.json_cache import get_cached_json, invalidate_json_cache, set_cached_json
from app.services.llm.model_list_cache import MODEL_LIST_CACHE_KEY, invalidate_model_list_cache


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


def test_content_list_cache_key_and_invalidation():
    invalidate_json_cache()
    params = ContentListCacheParams(
        page=1,
        page_size=50,
        hours=48,
    )
    key = params.key
    assert key == (
        "contents:list:page=1&page_size=50&include_trend_sources=0"
        "&sort_by=created_at&sort_order=desc&hours=48"
    )

    set_cached_json(key, {"items": [], "total": 0})
    set_cached_json("contents:favorites:list:1:20", {"items": []})
    invalidate_content_list_cache()

    assert get_cached_json(key, ttl_seconds=10) is None
    assert get_cached_json("contents:favorites:list:1:20", ttl_seconds=10) is not None
    invalidate_json_cache()


def test_model_list_cache_invalidation_is_scoped():
    invalidate_json_cache()
    set_cached_json(MODEL_LIST_CACHE_KEY, {"models": [], "total": 0})
    set_cached_json("models:usage:summary", {"total": {"calls": 1}})

    invalidate_model_list_cache()

    assert get_cached_json(MODEL_LIST_CACHE_KEY, ttl_seconds=10) is None
    assert get_cached_json("models:usage:summary", ttl_seconds=10) is not None
    invalidate_json_cache()
