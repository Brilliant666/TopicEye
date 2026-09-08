from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.auth import get_current_user
from app.api.v1.sources import router as sources_router
from app.core.database import Base, get_db
from app.models.content import ContentItem
from app.models.source import Source, SourceStatus
from app.repositories.source_repo import SourceRepository
from app.services import rardar_hotspot_news as news
from scripts import refresh_rardar_hotspot_news as cli


def test_source_pause_api_rejects_anonymous_and_non_admin():
    app = FastAPI()
    app.include_router(sources_router)

    async def no_database():
        yield object()  # Any accidental handler access fails rather than touches a database.

    app.dependency_overrides[get_db] = no_database
    with TestClient(app) as client:
        assert client.put("/sources/1", json={"enabled": False}).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role="user")
        assert client.put("/sources/1", json={"enabled": False}).status_code == 403


@pytest_asyncio.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def fetched():
    return news._FeedFetchResult(
        entries=[{"title": "Saved report", "url": "https://example.org/report", "summary": "Actual material"}],
        etag='"saved"',
        last_modified="Wed, 09 Sep 2026 00:00:00 GMT",
        not_modified=False,
    )


@pytest.mark.asyncio
async def test_pause_survives_reinitialization_and_repeated_refresh_then_resume(sessions, monkeypatch):
    definition = news.HOTSPOT_NEWS_SOURCES[0]
    calls = []

    async def fetch(source, _definition):
        calls.append((source.etag, source.last_modified))
        return fetched() if len(calls) == 1 else news._FeedFetchResult([], None, None, True)

    monkeypatch.setattr(news, "_fetch_source", fetch)
    async with sessions() as db:
        await news.refresh_hotspot_news(db, definitions=(definition,))
        source = (await db.execute(select(Source))).scalar_one()
        item = (await db.execute(select(ContentItem))).scalar_one()
        item.tags = {**item.tags, "quickReadSentinel": {"titleZh": "保留中文"}}
        await db.commit()
        original = (item.title, item.summary, dict(item.tags), source.etag, source.last_modified, source.last_sync_at)
        source.enabled = False
        source.status = SourceStatus.DISABLED
        await db.commit()
        for _ in range(2):
            result = await news.refresh_hotspot_news(db, definitions=(definition,))
            assert result.status == "paused"
            assert result.sources[0].status == "paused"
            assert result.sources[0].retained == 1
            assert not source.enabled and source.status == SourceStatus.DISABLED
        assert len(calls) == 1
        assert (item.title, item.summary, item.tags, source.etag, source.last_modified, source.last_sync_at) == original
        page, _ = await news.load_hotspot_news(db)
        assert page.totalItems == 1
        assert page.sources[0].status == "paused"
        assert page.sources[0].errorCode is None
        source.enabled = True
        source.status = SourceStatus.ACTIVE
        await db.commit()
        result = await news.refresh_hotspot_news(db, definitions=(definition,))
        assert result.sources[0].status == "not_modified"
        assert len(calls) == 2 and calls[1] == original[3:5]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_pause_during_fetch_not_overwritten_by_completion(sessions, monkeypatch, fail):
    definition = news.HOTSPOT_NEWS_SOURCES[0]

    async def fetch(source, _definition):
        async with sessions() as admin:
            await admin.execute(
                update(Source).where(Source.id == source.id).values(enabled=False, status=SourceStatus.DISABLED)
            )
            await admin.commit()
        if fail:
            raise RuntimeError("mock source failure")
        return fetched()

    monkeypatch.setattr(news, "_fetch_source", fetch)
    async with sessions() as db:
        await news.refresh_hotspot_news(db, definitions=(definition,))
    async with sessions() as db:
        source = (await db.execute(select(Source))).scalar_one()
        assert not source.enabled
        assert source.status == SourceStatus.DISABLED
        assert bool(source.sync_error) is fail
        result = await news.refresh_hotspot_news(db, definitions=(definition,))
        assert result.status == "paused"


@pytest.mark.asyncio
async def test_claim_reads_current_admin_choice_not_session_identity_cache(sessions):
    definition = news.HOTSPOT_NEWS_SOURCES[0]
    async with sessions() as db:
        source = await news._ensure_managed_source(db, news.RardarHotspotNewsRepository(db), definition, 0)
        await db.commit()
        async with sessions() as admin:
            await admin.execute(
                update(Source).where(Source.id == source.id).values(enabled=False, status=SourceStatus.DISABLED)
            )
            await admin.commit()
        assert await SourceRepository(db).claim_sync(source.id, lease_seconds=300) is None
        assert not source.enabled


@pytest.mark.asyncio
async def test_cli_paused_sources_share_rule_and_exit_normally(sessions, monkeypatch, capsys):
    async with sessions() as db:
        repository = news.RardarHotspotNewsRepository(db)
        for index, definition in enumerate(news.HOTSPOT_NEWS_SOURCES):
            source = await news._ensure_managed_source(db, repository, definition, index)
            source.enabled = False
            source.status = SourceStatus.DISABLED
        await db.commit()

    async def forbidden(*_args):
        pytest.fail("Paused CLI must not fetch")

    monkeypatch.setattr(news, "_fetch_source", forbidden)
    monkeypatch.setattr(cli, "async_session", sessions)
    monkeypatch.setattr(cli, "is_rardar_product", lambda: True)
    assert await cli._run() == 0
    assert '"status": "paused"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_other_sources_continue_and_later_pause_prevents_fetch(sessions, monkeypatch):
    definitions = news.HOTSPOT_NEWS_SOURCES[:3]
    calls = []

    async def fetch(source, definition):
        calls.append(definition.key)
        if definition == definitions[0]:
            async with sessions() as admin:
                await admin.execute(
                    update(Source)
                    .where(Source.url == definitions[1].feed_url)
                    .values(enabled=False, status=SourceStatus.DISABLED)
                )
                await admin.commit()
            raise RuntimeError("single source failure")
        return fetched()

    monkeypatch.setattr(news, "_fetch_source", fetch)
    async with sessions() as db:
        result = await news.refresh_hotspot_news(db, definitions=definitions)
        assert result.status == "degraded"
        assert [source.status for source in result.sources] == ["failed", "paused", "refreshed"]
        assert calls == [definitions[0].key, definitions[2].key]
        assert result.sources[2].retained == 1
