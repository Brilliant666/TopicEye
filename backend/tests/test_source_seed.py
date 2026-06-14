import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.source import Source
from app.services.source_seed import seed_default_sources


@pytest.mark.asyncio
async def test_seed_default_sources_is_idempotent(tmp_path):
    seed_path = tmp_path / "sources.json"
    seed_path.write_text(
        json.dumps(
            [
                {
                    "name": "Example Feed",
                    "source_type": "RSS",
                    "url": " HTTPS://Example.com/feed.xml ",
                    "category": "测试",
                    "platform": "Example",
                    "weight": 4,
                    "fetch_interval_minutes": 120,
                },
                {
                    "name": "RSSHub Route",
                    "source_type": "RSSHub",
                    "url": "sspai/index",
                    "category": "效率",
                    "platform": "少数派",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            created = await seed_default_sources(db, seed_path=seed_path)
            await db.commit()
            assert created == 2

        async with session_factory() as db:
            created = await seed_default_sources(db, seed_path=seed_path)
            await db.commit()
            assert created == 0

            rows = (await db.execute(select(Source).order_by(Source.sort_order))).scalars().all()
            assert [source.name for source in rows] == ["Example Feed", "RSSHub Route"]
            assert rows[0].url == "https://example.com/feed.xml"
            assert rows[0].weight == 4
            assert rows[0].fetch_interval_minutes == 120
            assert rows[0].last_sync_at is not None
            assert rows[1].url == "sspai/index"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_seed_default_sources_defers_existing_unsynced_source(tmp_path):
    seed_path = tmp_path / "sources.json"
    seed_path.write_text(
        json.dumps([{"name": "Example Feed", "url": "https://example.com/feed.xml"}]),
        encoding="utf-8",
    )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as db:
            db.add(Source(name="Example Feed", url="https://example.com/feed.xml"))
            await db.commit()

        before = datetime.now(timezone.utc).replace(tzinfo=None)
        async with session_factory() as db:
            created = await seed_default_sources(db, seed_path=seed_path)
            await db.commit()
            assert created == 0

            source = (await db.execute(select(Source))).scalar_one()
            assert source.last_sync_at is not None
            assert source.last_sync_at >= before
    finally:
        await engine.dispose()
