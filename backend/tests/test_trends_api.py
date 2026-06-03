import pytest

from app.api.v1 import trends as trends_api
from app.services import duckdb_service


class FailingAsyncSession:
    def __call__(self):
        raise AssertionError("SQLite fallback should not run after successful DuckDB query")


@pytest.mark.asyncio
async def test_topic_trends_empty_duckdb_result_does_not_fallback(monkeypatch):
    monkeypatch.setattr(duckdb_service, "query_trend_topics", lambda days=7: [])
    monkeypatch.setattr(trends_api, "async_session", FailingAsyncSession())

    payload = await trends_api.topic_trends(days=7)

    assert payload == {"days": 7, "trends": []}


@pytest.mark.asyncio
async def test_keyword_cloud_empty_duckdb_result_does_not_fallback(monkeypatch):
    monkeypatch.setattr(duckdb_service, "query_keyword_cloud", lambda days=7, limit=50: [])
    monkeypatch.setattr(trends_api, "async_session", FailingAsyncSession())

    payload = await trends_api.keyword_cloud(days=7, limit=60)

    assert payload == {"days": 7, "keywords": []}
