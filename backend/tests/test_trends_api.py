import pytest
from fastapi import HTTPException, Response

from app.api.v1 import trends as trends_api
from app.services import duckdb_service


class FailingAsyncSession:
    def __call__(self):
        raise AssertionError("SQLite fallback should not run after successful DuckDB query")


@pytest.mark.asyncio
async def test_topic_trends_empty_duckdb_result_does_not_fallback(monkeypatch):
    monkeypatch.setattr(duckdb_service, "query_trend_topics", lambda days=7: [])
    monkeypatch.setattr(trends_api, "async_session", FailingAsyncSession())

    response = Response()
    payload = await trends_api.topic_trends(response=response, days=7)

    assert payload == {"days": 7, "trends": []}
    assert response.headers["x-analytics-backend"] == "duckdb"


@pytest.mark.asyncio
async def test_keyword_cloud_empty_duckdb_result_does_not_fallback(monkeypatch):
    monkeypatch.setattr(duckdb_service, "query_keyword_cloud", lambda days=7, limit=50: [])
    monkeypatch.setattr(trends_api, "async_session", FailingAsyncSession())

    response = Response()
    payload = await trends_api.keyword_cloud(response=response, days=7, limit=60)

    assert payload == {"days": 7, "keywords": []}
    assert response.headers["x-analytics-backend"] == "duckdb"


@pytest.mark.asyncio
async def test_topic_trends_duckdb_error_returns_503_without_fallback(monkeypatch):
    def fail(days=7):
        raise RuntimeError("duckdb unavailable")

    monkeypatch.setattr(duckdb_service, "query_trend_topics", fail)
    monkeypatch.setattr(trends_api, "async_session", FailingAsyncSession())

    with pytest.raises(HTTPException) as exc_info:
        await trends_api.topic_trends(response=Response(), days=7)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "DuckDB analytical layer unavailable"


@pytest.mark.asyncio
async def test_keyword_cloud_duckdb_error_returns_503_without_fallback(monkeypatch):
    def fail(days=7, limit=50):
        raise RuntimeError("duckdb unavailable")

    monkeypatch.setattr(duckdb_service, "query_keyword_cloud", fail)
    monkeypatch.setattr(trends_api, "async_session", FailingAsyncSession())

    with pytest.raises(HTTPException) as exc_info:
        await trends_api.keyword_cloud(response=Response(), days=7, limit=60)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "DuckDB analytical layer unavailable"
