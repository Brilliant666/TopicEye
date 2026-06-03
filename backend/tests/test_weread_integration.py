from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.main  # noqa: F401 - import all models for Base.metadata
from app.api.v1.integrations import (
    delete_weread_integration,
    get_weread_integration,
    sync_weread,
    update_weread_integration,
)
from app.core.config import settings
from app.core.database import Base
from app.models.content import ContentItem
from app.models.source import Source, SourceStatus
from app.schemas.integration import IntegrationUpdateRequest
from app.services.auth_service import create_user
from app.services.integration_service import WEREAD_INSTALL_COMMAND
import app.services.weread_materials as weread_materials
from app.services.weread_materials import normalize_weread_entries


@pytest.mark.asyncio
async def test_weread_status_masks_api_key_and_reports_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "WEREAD_SKILL_API_URL", None)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="weread@example.com", password="Password123")
        status = await update_weread_integration(
            IntegrationUpdateRequest(api_key="wr_secret_1234567890"),
            user,
            db,
        )

        assert status["configured"] is True
        assert status["api_key_hint"] == "wr_s...7890"
        assert "wr_secret_1234567890" not in str(status)
        assert status["sync_endpoint_configured"] is False
        assert status["install_command"] == WEREAD_INSTALL_COMMAND

        fetched = await get_weread_integration(user, db)
        assert fetched["api_key_hint"] == "wr_s...7890"
        assert "wr_secret_1234567890" not in str(fetched)

    await engine.dispose()


def test_weread_api_key_rejects_blank_after_strip():
    with pytest.raises(ValueError):
        IntegrationUpdateRequest(api_key="        ")


@pytest.mark.asyncio
async def test_weread_integration_delete_clears_configuration(monkeypatch):
    monkeypatch.setattr(settings, "WEREAD_SKILL_API_URL", "http://127.0.0.1:9999/weread")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="delete-weread@example.com", password="Password123")
        configured = await update_weread_integration(
            IntegrationUpdateRequest(api_key="  wr_secret_delete_123456  ", config={"tag": "inbox"}),
            user,
            db,
        )
        assert configured["configured"] is True
        assert configured["api_key_hint"] == "wr_s...3456"
        assert configured["config"] == {"tag": "inbox"}

        deleted = await delete_weread_integration(user, db)
        assert deleted["configured"] is False
        assert deleted["api_key_hint"] is None
        assert deleted["config"] == {}

        fetched = await get_weread_integration(user, db)
        assert fetched["configured"] is False
        assert fetched["api_key_hint"] is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_weread_integration_is_scoped_to_current_user(monkeypatch):
    monkeypatch.setattr(settings, "WEREAD_SKILL_API_URL", None)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        owner = await create_user(db, email="owner-weread@example.com", password="Password123")
        other = await create_user(db, email="other-weread@example.com", password="Password123")
        await update_weread_integration(
            IntegrationUpdateRequest(api_key="wr_secret_owner_123456"),
            owner,
            db,
        )

        owner_status = await get_weread_integration(owner, db)
        other_status = await get_weread_integration(other, db)

        assert owner_status["configured"] is True
        assert owner_status["api_key_hint"] == "wr_s...3456"
        assert other_status["configured"] is False
        assert other_status["api_key_hint"] is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_weread_sync_without_endpoint_returns_actionable_error(monkeypatch):
    monkeypatch.setattr(settings, "WEREAD_SKILL_API_URL", None)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="sync-weread@example.com", password="Password123")
        await update_weread_integration(
            IntegrationUpdateRequest(api_key="wr_secret_1234567890"),
            user,
            db,
        )

        error = None
        try:
            await sync_weread(limit=50, current_user=user, db=db)
        except HTTPException as exc:
            error = exc

        assert error is not None
        assert error.status_code == 502
        assert "微信读书 Skill API endpoint 未配置" in str(error.detail)

        status = await get_weread_integration(user, db)
        assert status["last_sync_status"] == "error"
        assert "endpoint 未配置" in status["last_sync_error"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_weread_sync_imports_materials_and_deduplicates(monkeypatch):
    async def fake_fetch(api_key: str, *, limit: int = 50):
        assert api_key == "wr_secret_sync_123456"
        assert limit == 2
        return [
            {
                "title": "微信读书选题一",
                "url": "https://weread.qq.com/note/1",
                "author": "作者一",
                "summary": "第一条阅读笔记。",
                "raw_content": "第一条阅读笔记。",
            },
            {
                "title": "微信读书选题二",
                "url": "https://weread.qq.com/note/2",
                "author": "作者二",
                "summary": "第二条阅读笔记。",
                "raw_content": "第二条阅读笔记。",
            },
        ]

    monkeypatch.setattr(settings, "WEREAD_SKILL_API_URL", "http://127.0.0.1:9999/weread")
    monkeypatch.setattr(weread_materials, "fetch_weread_materials", fake_fetch)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = await create_user(db, email="sync-success-weread@example.com", password="Password123")
        await update_weread_integration(
            IntegrationUpdateRequest(api_key=" wr_secret_sync_123456 "),
            user,
            db,
        )

        first = await sync_weread(limit=2, current_user=user, db=db)
        assert first.fetched == 2
        assert first.new == 2
        assert first.duplicates == 0
        assert first.source_name == "微信读书素材"

        source = await db.scalar(select(Source).where(Source.name == "微信读书素材"))
        assert source is not None
        assert source.status == SourceStatus.ACTIVE
        assert source.sync_error is None

        rows = (
            await db.execute(
                select(ContentItem)
                .where(ContentItem.source_id == source.id)
                .order_by(ContentItem.title.asc())
            )
        ).scalars().all()
        assert [item.title for item in rows] == ["微信读书选题一", "微信读书选题二"]
        assert {item.platform for item in rows} == {"微信读书"}
        assert {item.category for item in rows} == {"阅读素材"}

        second = await sync_weread(limit=2, current_user=user, db=db)
        assert second.fetched == 2
        assert second.new == 0
        assert second.duplicates == 2

        status = await get_weread_integration(user, db)
        assert status["last_sync_status"] == "success"
        assert status["last_sync_error"] is None

    await engine.dispose()


def test_normalize_weread_entries_accepts_books_notes_and_highlights():
    payload = {
        "books": [
            {
                "title": "系统之美",
                "author": "德内拉",
                "coverUrl": "https://img.example.com/book.jpg",
                "bookUrl": "https://weread.qq.com/book-detail",
                "summary": "复杂系统的反馈结构。",
            }
        ],
        "notes": [
            {
                "bookTitle": "纳瓦尔宝典",
                "bookAuthor": "Eric Jorgenson",
                "markText": "判断力来自长期复利。",
                "reviewUrl": "https://weread.qq.com/note",
            }
        ],
        "highlights": [
            {
                "name": "写作是最小可行思考",
                "abstract": "把想法写下来，才知道自己是否真的想清楚。",
            }
        ],
    }

    entries = normalize_weread_entries(payload)

    assert len(entries) == 3
    assert entries[0]["title"] == "系统之美"
    assert entries[0]["author"] == "德内拉"
    assert entries[0]["cover_url"] == "https://img.example.com/book.jpg"
    assert entries[1]["title"] == "纳瓦尔宝典"
    assert entries[1]["raw_content"] == "判断力来自长期复利。"
    assert entries[2]["url"] == "https://weread.qq.com/r/weread-skills"
