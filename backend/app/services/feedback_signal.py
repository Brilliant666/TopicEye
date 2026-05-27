"""Helpers for converting user feedback into scoring signals."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import UserFeedback


async def get_feedback_scores(db: AsyncSession, content_ids: list[int]) -> dict[int, float]:
    """Return summed feedback score deltas keyed by content id."""
    if not content_ids:
        return {}

    result = await db.execute(
        select(
            UserFeedback.content_id,
            func.coalesce(func.sum(UserFeedback.score_delta), 0.0),
        )
        .where(UserFeedback.content_id.in_(content_ids))
        .group_by(UserFeedback.content_id)
    )
    return {int(content_id): float(score or 0) for content_id, score in result.all()}
