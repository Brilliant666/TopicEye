import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.api.v1.feedback import submit_feedback
from app.database import Base
from app.models.feedback import UserFeedback
from app.schemas.feedback import FeedbackCreate
from app.services.feedback_signal import get_feedback_scores


@pytest.mark.asyncio
async def test_feedback_overwrites_previous_signal_for_content():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        first = await submit_feedback(
            FeedbackCreate(content_id=1, feedback_type="great_pick", comment="up"),
            db,
        )
        second = await submit_feedback(
            FeedbackCreate(content_id=1, feedback_type="not_relevant", comment="down"),
            db,
        )

        assert second.id == first.id
        assert second.score_delta == -20.0

        scores = await get_feedback_scores(db, [1])
        assert scores == {1: -20.0}

    await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_overwrite_collapses_legacy_duplicates():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        db.add_all([
            UserFeedback(content_id=1, feedback_type="like", score_delta=10.0),
            UserFeedback(content_id=1, feedback_type="dislike", score_delta=-15.0),
        ])
        await db.flush()

        feedback = await submit_feedback(
            FeedbackCreate(content_id=1, feedback_type="great_pick", comment="revised"),
            db,
        )

        scores = await get_feedback_scores(db, [1])
        assert scores == {1: 20.0}
        assert feedback.comment == "revised"

    await engine.dispose()
