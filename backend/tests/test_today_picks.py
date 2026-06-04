import json

import pytest
from fastapi import FastAPI
import httpx

from app.api.v1 import contents as contents_api
from app.repositories.content_repo import ContentRepo
from app.services import today_picks
from app.services.json_cache import invalidate_json_cache


class FailingSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, *args, **kwargs):
        raise AssertionError("today-picks should not query SQLAlchemy for analytical reads")


def _failing_session_factory():
    return FailingSession()


def _duckdb_rows():
    return [
        {
            "id": 1,
            "title": "DuckDB 精选样本",
            "url": "https://example.com/pick",
            "source_id": 1,
            "source_name": "测试信源",
            "source_type": "RSS",
            "platform": "rss",
            "author": None,
            "published_at": None,
            "crawled_at": "2026-06-04T00:00:00",
            "content_hash": None,
            "summary": "原始摘要",
            "raw_content": None,
            "cover_url": None,
            "category": "AI",
            "tags": ["AI"],
            "language": "zh",
            "status": "analyzed",
            "is_favorited": False,
            "topic_id": 10,
            "duplicate_of": None,
            "similarity_score": 0.0,
            "created_at": "2026-06-04T00:00:00",
            "updated_at": "2026-06-04T00:00:00",
            "analysis_id": 101,
            "analysis_created_at": "2026-06-04T00:01:00",
            "quality_score": 80.0,
            "hot_score": 75.0,
            "freshness_score": 90.0,
            "creator_score": 86.0,
            "viral_score": 70.0,
            "risk_score": 15.0,
            "curation_score": 88.0,
            "info_density": 82.0,
            "actionability": 78.0,
            "recommended_reason": "值得写",
            "recommendation": "可以作为创作者选题",
            "ai_summary": "AI 分析摘要",
            "ai_tags": ["AI", "产品"],
            "enrichment_status": "pending",
            "enrichment": '{"why_matters":"测试"}',
            "source_weight": 5,
            "adjusted_curation_score": 104.0,
        },
        {
            "id": 2,
            "title": "重复样本",
            "url": "https://example.com/duplicate",
            "source_id": 1,
            "source_name": "测试信源",
            "source_type": "RSS",
            "platform": "rss",
            "published_at": None,
            "crawled_at": "2026-06-04T00:00:00",
            "category": "AI",
            "status": "analyzed",
            "is_favorited": False,
            "topic_id": 10,
            "duplicate_of": 1,
            "analysis_id": 102,
            "analysis_created_at": "2026-06-04T00:01:00",
            "creator_score": 80.0,
            "risk_score": 10.0,
            "curation_score": 90.0,
            "source_weight": 3,
            "adjusted_curation_score": 90.0,
        },
    ]


@pytest.mark.asyncio
async def test_build_today_picks_uses_duckdb_payload_without_orm(monkeypatch):
    async def fail_list_for_today_picks(*args, **kwargs):
        raise AssertionError("ContentRepo.list_for_today_picks should not be used")

    monkeypatch.setattr(ContentRepo, "list_for_today_picks", fail_list_for_today_picks)
    monkeypatch.setattr(
        today_picks,
        "query_today_picks",
        lambda hours=48, category=None, limit=None, curation_threshold=55: _duckdb_rows(),
    )
    monkeypatch.setattr(
        today_picks,
        "query_topics",
        lambda: [{"id": 10, "name": "AI 话题", "summary": "摘要", "keywords": ["AI"], "best_score": 104.0}],
    )

    payload = await today_picks.build_today_picks(FailingSession(), category="AI", hours=48, limit=1)

    assert payload["total"] == 1
    assert payload["duplicates_hidden"] == 1
    assert payload["page_size"] == 1
    assert payload["topics"] == [{"id": 10, "name": "AI 话题", "summary": "摘要", "keywords": ["AI"], "best_score": 104.0}]
    item = payload["items"][0]
    assert item["id"] == 1
    assert item["tags"] == ["AI"]
    assert item["analysis"]["id"] == 101
    assert item["analysis"]["tags"] == ["AI", "产品"]
    assert item["analysis"]["enrichment"] == {"why_matters": "测试"}
    assert item["analysis"]["adjusted_curation_score"] == 104.0
    assert item["analysis"]["score_breakdown"]["final_score"] == 104.0


@pytest.mark.asyncio
async def test_today_picks_api_cache_headers_and_duckdb_503(monkeypatch):
    invalidate_json_cache()
    monkeypatch.setattr(contents_api.settings, "READ_CACHE_TTL_SECONDS", 60)
    monkeypatch.setattr(contents_api, "async_session", _failing_session_factory)

    app = FastAPI()
    app.include_router(contents_api.router)
    transport = httpx.ASGITransport(app=app)

    calls = {"count": 0}

    async def fake_build_today_picks(db, *, category=None, hours=48, limit=None):
        calls["count"] += 1
        return {"items": [], "total": 0, "duplicates_hidden": 0, "topics": [], "page": 1, "page_size": 0}

    monkeypatch.setattr("app.services.today_picks.build_today_picks", fake_build_today_picks)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/contents/today-picks?time_range=48h")
        second = await client.get("/contents/today-picks?time_range=48h")

    assert first.status_code == 200
    assert first.headers["x-analytics-backend"] == "duckdb"
    assert first.headers["x-today-picks-cache"] == "MISS"
    assert second.status_code == 200
    assert second.headers["x-analytics-backend"] == "duckdb"
    assert second.headers["x-today-picks-cache"].startswith("HIT")
    assert calls["count"] == 1

    invalidate_json_cache()

    async def fail_build_today_picks(db, *, category=None, hours=48, limit=None):
        raise RuntimeError("duckdb unavailable")

    monkeypatch.setattr("app.services.today_picks.build_today_picks", fail_build_today_picks)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        failed = await client.get("/contents/today-picks?time_range=24h")

    assert failed.status_code == 503
    assert json.loads(failed.text)["detail"] == "DuckDB analytical layer unavailable"
    invalidate_json_cache()
