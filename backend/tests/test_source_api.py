from __future__ import annotations

from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.main  # noqa: F401 - import all models for Base.metadata
import app.api.v1.sources as sources_api
from app.api.v1.sources import create_source, router as sources_router, update_source
from app.core.database import Base
from app.core.dependencies import get_db
from app.models.source import Source, SourceStatus, SourceType
from app.schemas.source import SourceCreate, SourceUpdate
from app.services.source_cache import invalidate_source_list_cache


@pytest_asyncio.fixture
async def sources_http_client(monkeypatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    invalidate_source_list_cache()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(sources_api, "async_session", session_factory)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(sources_router)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    invalidate_source_list_cache()
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_source_strips_name_and_url():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        source = await create_source(
            SourceCreate(
                name="  Example Feed  ",
                url="  https://example.com/rss.xml  ",
                source_type=SourceType.RSS,
            ),
            db,
        )

        assert source.name == "Example Feed"
        assert source.url == "https://example.com/rss.xml"
        assert source.sort_order == 10

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_source_rejects_duplicate_url():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        await create_source(
            SourceCreate(name="A", url="https://example.com/rss.xml", source_type=SourceType.RSS),
            db,
        )

        error = None
        try:
            await create_source(
                SourceCreate(name="B", url=" https://example.com/rss.xml ", source_type=SourceType.RSS),
                db,
            )
        except HTTPException as exc:
            error = exc

        assert error is not None
        assert error.status_code == 409
        assert error.detail == "信源 URL 已存在"

    await engine.dispose()


@pytest.mark.asyncio
async def test_update_source_rejects_duplicate_url():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        source_a = await create_source(
            SourceCreate(name="A", url="https://example.com/a.xml", source_type=SourceType.RSS),
            db,
        )
        source_b = await create_source(
            SourceCreate(name="B", url="https://example.com/b.xml", source_type=SourceType.RSS),
            db,
        )

        error = None
        try:
            await update_source(
                source_b.id,
                SourceUpdate(url=source_a.url),
                db,
            )
        except HTTPException as exc:
            error = exc

        assert error is not None
        assert error.status_code == 409
        assert error.detail == "信源 URL 已存在"

    await engine.dispose()


def test_source_create_rejects_invalid_url_after_strip():
    with pytest.raises(ValidationError):
        SourceCreate(name="Bad", url="  ftp://example.com/feed.xml  ")


def test_source_create_normalizes_uppercase_http_scheme():
    source = SourceCreate(name="Upper", url=" HTTPS://example.com/feed.xml ")

    assert source.url == "https://example.com/feed.xml"


def test_source_create_normalizes_optional_text_fields():
    source = SourceCreate(
        name="Feed",
        url="https://example.com/feed.xml",
        source_type=SourceType.RSS,
        keyword="   ",
        platform="  RSSHub  ",
        category="  AI  ",
    )

    assert source.keyword is None
    assert source.platform == "RSSHub"
    assert source.category == "AI"


def test_source_update_normalizes_optional_text_fields():
    update = SourceUpdate(
        name="  Feed  ",
        keyword="  topic  ",
        platform="   ",
        category="  News  ",
        sync_error="   ",
    )

    assert update.name == "Feed"
    assert update.keyword == "topic"
    assert update.platform is None
    assert update.category == "News"
    assert update.sync_error is None


def test_parse_source_batch_normalizes_urls_and_skips_invalid_protocols():
    content = """
    [
      {"title": "JSON Feed", "url": " HTTPS://example.com/feed.xml "},
      {"title": "Bad Feed", "url": " ftp://example.com/feed.xml "}
    ]
    """

    items = sources_api._parse_source_batch(content, "导入")

    assert len(items) == 1
    assert items[0]["name"] == "JSON Feed"
    assert items[0]["url"] == "https://example.com/feed.xml"


@pytest.mark.asyncio
async def test_preview_batch_uses_default_category_for_blank_input(
    sources_http_client: httpx.AsyncClient,
):
    preview = await sources_http_client.post(
        "/sources/preview-batch",
        json={
            "content": '[{"title": "Feed", "url": "https://example.com/feed.xml"}]',
            "category": "   ",
        },
    )

    assert preview.status_code == 200
    payload = preview.json()
    assert payload["total"] == 1
    assert payload["items"][0]["category"] == "批量导入"


@pytest.mark.asyncio
async def test_import_opml_normalizes_urls_and_skips_invalid_protocols(
    sources_http_client: httpx.AsyncClient,
):
    opml = """<?xml version="1.0" encoding="UTF-8"?>
    <opml version="2.0">
      <body>
        <outline text="Valid Feed" xmlUrl=" HTTPS://example.com/valid.xml "/>
        <outline text="Invalid Feed" xmlUrl="ftp://example.com/invalid.xml"/>
      </body>
    </opml>
    """

    imported = await sources_http_client.post(
        "/sources/import-opml",
        files={"file": ("feeds.opml", opml, "text/xml")},
    )
    assert imported.status_code == 200
    assert imported.json()["created"] == 1
    assert imported.json()["skipped"] == 0
    assert imported.json()["total"] == 2

    listed = await sources_http_client.get("/sources?page=1&page_size=20")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Valid Feed"
    assert payload["items"][0]["url"] == "https://example.com/valid.xml"


@pytest.mark.asyncio
async def test_sync_source_error_state_persists_over_http(
    sources_http_client: httpx.AsyncClient,
    monkeypatch,
):
    async def fake_ingest_from_source(source: Source, db: AsyncSession):
        source.status = SourceStatus.ERROR
        source.sync_error = "API endpoint unavailable"
        await db.flush()
        return {"fetched": 0, "new": 0, "duplicates": 0}

    monkeypatch.setattr(sources_api, "ingest_from_source", fake_ingest_from_source)

    created = await sources_http_client.post(
        "/sources",
        json={
            "name": "Broken API",
            "url": "https://example.com/api/news",
            "source_type": "API",
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    failed = await sources_http_client.post(f"/sources/{source_id}/sync")
    assert failed.status_code == 502
    assert failed.json()["detail"] == "API endpoint unavailable"

    persisted = await sources_http_client.get(f"/sources/{source_id}")
    assert persisted.status_code == 200
    assert persisted.json()["status"] == "error"
    assert persisted.json()["sync_error"] == "API endpoint unavailable"


@pytest.mark.asyncio
async def test_sync_disabled_source_is_rejected_without_ingest(
    sources_http_client: httpx.AsyncClient,
    monkeypatch,
):
    async def fail_ingest_from_source(source: Source, db: AsyncSession):
        raise AssertionError("disabled source should not be ingested")

    monkeypatch.setattr(sources_api, "ingest_from_source", fail_ingest_from_source)

    created = await sources_http_client.post(
        "/sources",
        json={
            "name": "Paused API",
            "url": "https://example.com/paused-api",
            "source_type": "API",
            "enabled": False,
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    failed = await sources_http_client.post(f"/sources/{source_id}/sync")
    assert failed.status_code == 409
    assert failed.json()["detail"] == "信源已禁用，请启用后再同步"

    persisted = await sources_http_client.get(f"/sources/{source_id}")
    assert persisted.status_code == 200
    assert persisted.json()["enabled"] is False
    assert persisted.json()["status"] == "active"


@pytest.mark.asyncio
async def test_source_list_cache_header_and_sync_error_invalidation(
    sources_http_client: httpx.AsyncClient,
    monkeypatch,
):
    created = await sources_http_client.post(
        "/sources",
        json={
            "name": "Cached API",
            "url": "https://example.com/cached-api",
            "source_type": "API",
        },
    )
    assert created.status_code == 201
    source_id = created.json()["id"]

    first_list = await sources_http_client.get("/sources?page=1&page_size=20")
    assert first_list.status_code == 200
    assert first_list.headers["x-sources-cache"] == "MISS"

    cached_list = await sources_http_client.get("/sources?page=1&page_size=20")
    assert cached_list.status_code == 200
    assert cached_list.headers["x-sources-cache"] == "HIT"
    assert cached_list.headers["x-sources-cache-age-ms"].isdigit()

    async def fake_ingest_from_source(source: Source, db: AsyncSession):
        source.status = SourceStatus.ERROR
        source.sync_error = "API endpoint unavailable"
        await db.flush()
        return {"fetched": 0, "new": 0, "duplicates": 0}

    monkeypatch.setattr(sources_api, "ingest_from_source", fake_ingest_from_source)

    failed = await sources_http_client.post(f"/sources/{source_id}/sync")
    assert failed.status_code == 502

    after_sync = await sources_http_client.get("/sources?page=1&page_size=20")
    assert after_sync.status_code == 200
    assert after_sync.headers["x-sources-cache"] == "MISS"
    payload = after_sync.json()
    assert payload["items"][0]["status"] == "error"
    assert payload["items"][0]["sync_error"] == "API endpoint unavailable"
