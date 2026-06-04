from app.api.v1 import stats
from app.services.json_cache import get_cached_json, invalidate_json_cache

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_stats_cache_headers_are_stable_hit_miss(monkeypatch):
    invalidate_json_cache()
    monkeypatch.setattr(stats.settings, "READ_CACHE_TTL_SECONDS", 60)
    monkeypatch.setattr(stats, "query_stats_source_distribution", lambda days=7: {"sources": []})

    first = await stats.get_source_distribution(days=7)
    assert first.headers["X-Analytics-Backend"] == "duckdb"
    assert first.headers["X-Stats-Cache"] == "MISS"
    assert "X-Stats-Cache-Age-Ms" not in first.headers

    second = await stats.get_source_distribution(days=7)
    assert second.headers["X-Analytics-Backend"] == "duckdb"
    assert second.headers["X-Stats-Cache"] == "HIT"
    assert float(second.headers["X-Stats-Cache-Age-Ms"]) >= 0

    invalidate_json_cache()


@pytest.mark.asyncio
async def test_stats_query_failure_returns_503_without_cache(monkeypatch):
    invalidate_json_cache()
    monkeypatch.setattr(stats.settings, "READ_CACHE_TTL_SECONDS", 60)

    def fail_query(days=7):
        raise RuntimeError("duckdb attach failed")

    monkeypatch.setattr(stats, "query_dashboard_stats", fail_query)

    with pytest.raises(HTTPException) as exc_info:
        await stats.get_dashboard_stats(days=7)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "DuckDB analytical layer unavailable"
    assert get_cached_json("stats:dashboard:7", ttl_seconds=60) is None

    invalidate_json_cache()


@pytest.mark.asyncio
async def test_dashboard_stats_cache_returns_workspace_payload(monkeypatch):
    invalidate_json_cache()
    monkeypatch.setattr(stats.settings, "READ_CACHE_TTL_SECONDS", 60)
    monkeypatch.setattr(
        stats,
        "query_dashboard_stats",
        lambda days=7: {
            "overview": {"total": 1, "analyzed": 1, "curated": 1, "today_new": 1},
            "sources": [{"source_name": "测试信源", "source_type": "rss", "content_count": 1, "curated_count": 1, "curation_rate": 100}],
            "categories": [{"category": "AI", "content_count": 1, "avg_score": 82}],
            "trend": [{"date": "2026-06-04", "content_count": 1, "curated_count": 1, "analyzed_count": 1}],
            "platforms": [{"name": "番茄小说", "table": "fanqie", "count": 1, "last_sync": None}],
            "kpi": {"total_crawled": 1, "total_curated": 1, "avg_curation": 82, "active_sources": 1},
            "source_breakdown": [{"source_name": "测试信源", "source_type": "rss", "content_count": 1, "curated_count": 1, "avg_score": 82}],
            "daily_trend": [{"date": "2026-06-04", "content_count": 1, "curated_count": 1, "avg_curation": 82}],
        },
    )

    first = await stats.get_dashboard_stats(days=7)
    assert first.headers["X-Analytics-Backend"] == "duckdb"
    assert first.headers["X-Stats-Cache"] == "MISS"
    assert b'"overview"' in first.body
    assert b'"sources"' in first.body
    assert b'"categories"' in first.body
    assert b'"trend"' in first.body
    assert b'"platforms"' in first.body
    assert b'"kpi"' in first.body

    second = await stats.get_dashboard_stats(days=7)
    assert second.headers["X-Stats-Cache"] == "HIT"

    invalidate_json_cache()
