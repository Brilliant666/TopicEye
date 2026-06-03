from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.main  # noqa: F401 - import all models for Base.metadata
from app.api.v1.sources import create_source, update_source
from app.core.database import Base
from app.models.source import SourceType
from app.schemas.source import SourceCreate, SourceUpdate


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
