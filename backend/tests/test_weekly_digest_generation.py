from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.weekly_digest import WeeklyDigest
from app.services import weekly_digest
from app.services.weekly_digest import DIGEST_GENERATING_STALE_AFTER, generate_weekly_digest


@pytest.mark.asyncio
async def test_generate_weekly_digest_returns_active_generating_without_fetch(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = datetime(2026, 5, 27, 12, 0, 0)
    monkeypatch.setattr(weekly_digest, "_utc_now", lambda: now)

    async def fail_fetch(*_args, **_kwargs):
        raise AssertionError("active GENERATING digest should not fetch inputs")

    monkeypatch.setattr(weekly_digest, "_fetch_weekly_analyzed", fail_fetch)
    async with session_factory() as db:
        existing = WeeklyDigest(
            week_key="2026-W21",
            week_label="5月18日 ~ 5月24日",
            week_start="2026-05-18",
            week_end="2026-05-24",
            status="GENERATING",
            updated_at=now - timedelta(minutes=1),
        )
        db.add(existing)
        await db.commit()

        digest = await generate_weekly_digest(db, reference_date=date(2026, 5, 27))

    assert digest.id == existing.id
    assert digest.status == "GENERATING"
    await engine.dispose()


@pytest.mark.asyncio
async def test_generate_weekly_digest_reclaims_stale_generating(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = datetime(2026, 5, 27, 12, 0, 0)
    monkeypatch.setattr(weekly_digest, "_utc_now", lambda: now)

    async def fake_fetch(*_args, **_kwargs):
        return []

    monkeypatch.setattr(weekly_digest, "_fetch_weekly_analyzed", fake_fetch)
    async with session_factory() as db:
        existing = WeeklyDigest(
            week_key="2026-W21",
            week_label="5月18日 ~ 5月24日",
            week_start="2026-05-18",
            week_end="2026-05-24",
            status="GENERATING",
            updated_at=now - DIGEST_GENERATING_STALE_AFTER - timedelta(seconds=1),
        )
        db.add(existing)
        await db.commit()

        digest = await generate_weekly_digest(db, reference_date=date(2026, 5, 27))

    assert digest.id == existing.id
    assert digest.status == "ERROR"
    assert "暂无分析数据" in digest.overview
    await engine.dispose()
