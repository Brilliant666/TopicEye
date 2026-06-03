from app.api.v1 import stats
from app.services.json_cache import invalidate_json_cache

import pytest


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
