from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.content import ContentItem
from app.models.source import Source, SourceStatus, SourceType
from app.services import content_pipeline
from app.services.content_pipeline import _build_http_client_kwargs, _update_source_error


def test_update_source_error_uses_readable_fallback_for_blank_message():
    source = Source(
        name="Broken API",
        url="https://example.com/api/news",
        source_type=SourceType.API,
    )

    _update_source_error(source, "")

    assert source.status == SourceStatus.ERROR
    assert source.sync_error == "信源同步失败"
    assert source.last_sync_at is not None


def test_build_http_client_kwargs_skips_explicit_proxy_for_loopback(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")

    local_kwargs = _build_http_client_kwargs("http://127.0.0.1:8999/api/news")
    remote_kwargs = _build_http_client_kwargs("https://example.com/api/news")

    assert local_kwargs["trust_env"] is False
    assert "proxy" not in local_kwargs
    assert remote_kwargs["trust_env"] is False
    assert remote_kwargs["proxy"] == "http://127.0.0.1:7890"


@pytest.mark.asyncio
async def test_ingest_from_source_reuses_category_names_per_source(monkeypatch):
    class FakeScraper:
        def __init__(self, source_url, source_config):
            self.source_url = source_url
            self.source_config = source_config

        async def fetch(self, client):
            return [
                {"title": "first", "url": "https://example.com/first", "summary": "one"},
                {"title": "second", "url": "https://example.com/second", "summary": "two"},
            ]

    category_loads = 0
    classified_with = []

    async def fake_get_active_category_names(db):
        nonlocal category_loads
        category_loads += 1
        return ["AI", "产品"]

    async def fake_classify_async(title, summary, db, category_names=None):
        classified_with.append(category_names)
        return {"category": "AI", "tags": ["ai"], "is_new_category": False, "confidence": 0.8}

    monkeypatch.setattr(content_pipeline, "get_scraper_cls", lambda source_type: FakeScraper)
    monkeypatch.setattr(content_pipeline, "_get_active_category_names", fake_get_active_category_names)
    monkeypatch.setattr(content_pipeline, "classify_async", fake_classify_async)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as db:
            source = Source(
                id=1,
                name="Example",
                url="https://example.com/feed",
                source_type=SourceType.RSS,
                enabled=True,
            )
            db.add(source)
            await db.commit()

            stats = await content_pipeline.ingest_from_source(source, db)
            await db.commit()

            rows = (await db.execute(select(ContentItem).order_by(ContentItem.id))).scalars().all()

        assert stats == {"fetched": 2, "new": 2, "duplicates": 0}
        assert category_loads == 1
        assert classified_with == [["AI", "产品"], ["AI", "产品"]]
        assert [row.category for row in rows] == ["AI", "AI"]
    finally:
        await engine.dispose()
