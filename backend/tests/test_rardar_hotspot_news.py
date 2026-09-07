from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.rardar import router as rardar_router
from app.core.config import settings
from app.core.database import get_db
from app.models.content import ContentItem
from app.models.source import Source, SourceStatus
from app.services import rardar_hotspot_news as news_service
from app.services.rardar_hotspot_news import (
    HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE,
    HOTSPOT_NEWS_PLATFORM,
    HOTSPOT_NEWS_SOURCES,
    _FeedFetchResult,
    load_hotspot_news,
    normalize_news_url,
    refresh_hotspot_news,
)


def _entry(
    *,
    url: str = "https://github.blog/changelog/2026-09-08-example/?utm_source=feed#section",
    title: str = "A concrete platform change",
    summary: str = "<p>The API now exposes a bounded, documented capability.</p>",
) -> dict:
    return {
        "url": url,
        "title": title,
        "summary": summary,
        "author": "GitHub",
        "published_at": datetime(2026, 9, 8, 1, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 8, 2, 0, tzinfo=UTC),
        "tags": ["API"],
    }


def test_normalize_news_url_removes_tracking_but_not_meaningful_query():
    assert (
        normalize_news_url("HTTPS://Example.COM:443/post?utm_source=rss&version=2&fbclid=ignored#fragment")
        == "https://example.com/post?version=2"
    )
    with pytest.raises(ValueError, match="news_item_url_invalid"):
        normalize_news_url("http://127.0.0.1/private")
    with pytest.raises(ValueError, match="news_item_url_invalid"):
        normalize_news_url("javascript:alert(1)")


@pytest.mark.asyncio
async def test_refresh_is_zero_model_deduplicated_and_truthful(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]
    calls = 0

    async def fake_fetch(source):
        nonlocal calls
        calls += 1
        return _FeedFetchResult(
            entries=[_entry(), _entry(url="https://github.blog/changelog/2026-09-08-example/?utm_medium=rss")],
            etag='"v1"',
            last_modified="Tue, 08 Sep 2026 02:00:00 GMT",
            not_modified=False,
        )

    monkeypatch.setattr(news_service, "_fetch_feed", fake_fetch)
    first = await refresh_hotspot_news(db, definitions=(definition,))
    second = await refresh_hotspot_news(db, definitions=(definition,))

    rows = (await db.execute(select(ContentItem))).scalars().all()
    source = (await db.execute(select(Source))).scalar_one()
    assert first.status == "completed"
    assert first.providerCalls == 0
    assert first.sources[0].created == 1
    assert second.sources[0].created == 0
    assert second.sources[0].duplicates == 2
    assert calls == 2
    assert len(rows) == 1
    assert rows[0].url == "https://github.blog/changelog/2026-09-08-example/"
    assert rows[0].summary == "The API now exposes a bounded, documented capability."
    assert rows[0].published_at == datetime(2026, 9, 8, 1, 0)
    assert rows[0].skip_analysis is True
    assert rows[0].skip_reason == "rardar_hotspot_news_zero_model_ingestion"
    assert source.platform == HOTSPOT_NEWS_PLATFORM
    assert source.hidden is True
    assert source.etag == '"v1"'

    loaded, _ = await load_hotspot_news(db)
    assert loaded.status == "ready"
    assert loaded.itemCount == 1
    assert loaded.items[0].publishedAt == datetime(2026, 9, 8, 1, 0, tzinfo=UTC)
    assert loaded.items[0].updatedAt == datetime(2026, 9, 8, 2, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_304_preserves_saved_rows(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]
    results = [
        _FeedFetchResult(entries=[_entry()], etag='"v1"', last_modified=None, not_modified=False),
        _FeedFetchResult(entries=[], etag='"v1"', last_modified=None, not_modified=True),
    ]

    async def fake_fetch(source):
        return results.pop(0)

    monkeypatch.setattr(news_service, "_fetch_feed", fake_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))
    before = (await db.execute(select(ContentItem))).scalar_one()
    before_fetched = before.crawled_at
    before_summary = before.summary

    repeated = await refresh_hotspot_news(db, definitions=(definition,))
    after = (await db.execute(select(ContentItem))).scalar_one()

    assert repeated.sources[0].status == "not_modified"
    assert after.id == before.id
    assert after.crawled_at == before_fetched
    assert after.summary == before_summary


@pytest.mark.asyncio
async def test_refresh_bounds_large_feeds_to_the_newest_entries(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]
    entries = [
        {
            **_entry(url=f"https://example.com/news/{index}"),
            "published_at": datetime(2026, 9, 8, index % 24, tzinfo=UTC),
        }
        for index in range(HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE + 5)
    ]

    async def fake_fetch(source):
        return _FeedFetchResult(entries=entries, etag=None, last_modified=None, not_modified=False)

    monkeypatch.setattr(news_service, "_fetch_feed", fake_fetch)
    result = await refresh_hotspot_news(db, definitions=(definition,))

    rows = (await db.execute(select(ContentItem))).scalars().all()
    assert result.sources[0].fetched == HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE + 5
    assert result.sources[0].created == HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE
    assert len(rows) == HOTSPOT_NEWS_MAX_ENTRIES_PER_SOURCE


@pytest.mark.asyncio
async def test_source_failure_preserves_old_content_and_degrades_independently(db, monkeypatch):
    first, second = HOTSPOT_NEWS_SOURCES[:2]

    async def initial_fetch(source):
        suffix = "github" if source.url == first.feed_url else "hugging-face"
        return _FeedFetchResult(
            entries=[_entry(url=f"https://example.com/{suffix}", title=f"{suffix} change")],
            etag=None,
            last_modified=None,
            not_modified=False,
        )

    monkeypatch.setattr(news_service, "_fetch_feed", initial_fetch)
    await refresh_hotspot_news(db, definitions=(first, second))

    async def partial_failure(source):
        if source.url == first.feed_url:
            raise RuntimeError("token=should-not-be-exposed")
        return _FeedFetchResult(entries=[], etag=None, last_modified=None, not_modified=True)

    monkeypatch.setattr(news_service, "_fetch_feed", partial_failure)
    result = await refresh_hotspot_news(db, definitions=(first, second))
    loaded, _ = await load_hotspot_news(db)

    assert result.status == "degraded"
    assert result.providerCalls == 0
    assert len(loaded.items) == 2
    assert loaded.status == "degraded"
    states = {source.key: source.status for source in loaded.sources}
    assert states[first.key] == "failed"
    assert states[second.key] == "healthy"
    failed_source = (await db.execute(select(Source).where(Source.url == first.feed_url))).scalar_one()
    assert failed_source.status == SourceStatus.ERROR
    assert "should-not-be-exposed" not in (failed_source.sync_error or "")


@pytest.mark.asyncio
async def test_saved_news_api_never_fetches_sources_or_models(db, monkeypatch):
    definition = HOTSPOT_NEWS_SOURCES[0]

    async def initial_fetch(source):
        return _FeedFetchResult(entries=[_entry()], etag=None, last_modified=None, not_modified=False)

    monkeypatch.setattr(news_service, "_fetch_feed", initial_fetch)
    await refresh_hotspot_news(db, definitions=(definition,))

    async def forbidden_fetch(source):
        raise AssertionError("GET must not fetch a source")

    monkeypatch.setattr(news_service, "_fetch_feed", forbidden_fetch)
    monkeypatch.setattr(settings, "RARDAR_PRODUCT_MODE", True)

    app = FastAPI()
    app.include_router(rardar_router, prefix="/api/v1")

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/rardar/hotspot-news")
        filtered = await client.get(f"/api/v1/rardar/hotspot-news?source={definition.key}")
        unknown = await client.get("/api/v1/rardar/hotspot-news?source=unknown")

    assert response.status_code == 200
    assert response.json()["itemCount"] == 1
    assert filtered.status_code == 200
    assert filtered.json()["selectedSource"] == definition.key
    assert unknown.status_code == 422
