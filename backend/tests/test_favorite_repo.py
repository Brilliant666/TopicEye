from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.content import ContentItem, ContentStatus
from app.models.favorite import FavoriteTargetType
from app.repositories.favorite_repo import FavoriteRepo
from app.schemas.favorite import FavoriteCreate


@pytest.mark.asyncio
async def test_content_favorite_upsert_builds_snapshot_and_dedupes():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        db.add(
            ContentItem(
                id=1,
                title="测试选题",
                url="https://example.com/topic",
                source_name="测试源",
                source_type="RSS",
                category="AI",
                status=ContentStatus.ANALYZED,
                crawled_at=datetime.utcnow(),
            )
        )
        await db.flush()

        repo = FavoriteRepo(db)
        first = await repo.upsert(FavoriteCreate(target_type=FavoriteTargetType.CONTENT, target_id=1))
        second = await repo.upsert(FavoriteCreate(target_type=FavoriteTargetType.CONTENT, target_id=1, note="研究一下"))

        assert second.id == first.id
        assert second.title == "测试选题"
        assert second.target_key == "1"
        assert second.note == "研究一下"
        assert second.snapshot["category"] == "AI"

        items, total = await repo.list_paginated(target_type=FavoriteTargetType.CONTENT)
        assert total == 1
        assert items[0].id == first.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_external_favorite_requires_title_when_target_not_resolved():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        repo = FavoriteRepo(db)
        with pytest.raises(ValueError):
            await repo.upsert(FavoriteCreate(target_type=FavoriteTargetType.BOOK, target_key="fanqie:1"))

        item = await repo.upsert(
            FavoriteCreate(
                target_type=FavoriteTargetType.BOOK,
                target_key="fanqie:1",
                title="番茄测试书",
                url="https://example.com/book",
            )
        )
        assert item.target_type == FavoriteTargetType.BOOK
        assert item.target_key == "fanqie:1"

    await engine.dispose()
