import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from types import SimpleNamespace

from app.api.v1.feedback import submit_feedback
from app.core.database import Base
from app.models.content import ContentItem, ContentStatus
from app.models.feedback import UserFeedback
from app.schemas.feedback import FeedbackCreate
from app.services.feedback_signal import get_feedback_scores


def feedback_content(content_id: int = 1) -> ContentItem:
    return ContentItem(
        id=content_id,
        title=f"反馈样本 {content_id}",
        url=f"https://example.com/feedback/{content_id}",
        source_name="测试信源",
        source_type="RSS",
        status=ContentStatus.ANALYZED,
    )


@pytest.mark.asyncio
async def test_feedback_aggregates_multiple_users_and_updates_own_vote():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        db.add(feedback_content(1))
        await db.flush()

        first = await submit_feedback(
            FeedbackCreate(content_id=1, feedback_type="great_pick", comment="up"),
            db,
            SimpleNamespace(id=1),
        )
        second = await submit_feedback(
            FeedbackCreate(content_id=1, feedback_type="like", comment="also useful"),
            db,
            SimpleNamespace(id=2),
        )
        revised = await submit_feedback(
            FeedbackCreate(content_id=1, feedback_type="not_relevant", comment="down"),
            db,
            SimpleNamespace(id=1),
        )

        assert revised.id == first.id
        assert revised.user_id == 1
        assert revised.score_delta == -20.0
        assert second.id != first.id
        assert second.user_id == 2
        assert second.score_delta == 10.0

        scores = await get_feedback_scores(db, [1])
        assert scores == {1: -10.0}

    await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_overwrite_collapses_legacy_duplicates():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        db.add(feedback_content(1))
        await db.flush()
        db.add_all([
            UserFeedback(user_id=1, content_id=1, feedback_type="like", score_delta=10.0),
            UserFeedback(user_id=1, content_id=1, feedback_type="dislike", score_delta=-15.0),
            UserFeedback(user_id=2, content_id=1, feedback_type="like", score_delta=10.0),
        ])
        await db.flush()

        feedback = await submit_feedback(
            FeedbackCreate(content_id=1, feedback_type="great_pick", comment="revised"),
            db,
            SimpleNamespace(id=1),
        )

        scores = await get_feedback_scores(db, [1])
        assert scores == {1: 30.0}
        assert feedback.comment == "revised"

    await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_rejects_missing_content():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        with pytest.raises(HTTPException) as exc_info:
            await submit_feedback(
                FeedbackCreate(content_id=404, feedback_type="great_pick", comment="missing"),
                db,
                SimpleNamespace(id=1),
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Content not found"

    await engine.dispose()
