"""
Feedback service — scoring helpers consumed by the scoring engine.

Provides:
  - get_content_feedback_score: cumulative feedback score for a single content item
  - get_source_feedback_multiplier: 0.8-1.2 multiplier based on a source's feedback performance
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.feedback import UserFeedback
from app.models.content import ContentItem


async def get_content_feedback_score(
    db: AsyncSession, content_id: int
) -> float:
    """Return the cumulative feedback score delta for a content item.

    Returns 0.0 if no feedback exists.
    """
    result = await db.execute(
        select(func.coalesce(func.sum(UserFeedback.score_delta), 0.0)).where(
            UserFeedback.content_id == content_id
        )
    )
    return float(result.scalar() or 0.0)


async def get_source_feedback_multiplier(
    db: AsyncSession, source_id: int
) -> float:
    """Return a multiplier in the range [0.8, 1.2] based on feedback
    performance of all content items belonging to this source.

    Logic:
      - Compute average cumulative feedback score across all content items
        that belong to the source and have at least one feedback.
      - Normalize into 0.8-1.2 range using tanh scaling:
            multiplier = 1.0 + 0.2 * tanh(avg_score / 50)
        This means:
          avg_score =  0  → multiplier = 1.0  (neutral)
          avg_score = +50 → multiplier ≈ 1.19 (strong positive)
          avg_score = -50 → multiplier ≈ 0.81 (strong negative)
      - If no feedback exists for the source, return 1.0 (neutral).
    """
    import math

    # Sum feedback per content item for this source, then average
    subq = (
        select(
            UserFeedback.content_id,
            func.sum(UserFeedback.score_delta).label("total_delta"),
        )
        .join(ContentItem, ContentItem.id == UserFeedback.content_id)
        .where(ContentItem.source_id == source_id)
        .group_by(UserFeedback.content_id)
        .subquery()
    )

    result = await db.execute(select(func.avg(subq.c.total_delta)))
    avg_score = result.scalar()

    if avg_score is None:
        return 1.0

    multiplier = 1.0 + 0.2 * math.tanh(float(avg_score) / 50.0)
    return round(max(0.8, min(1.2, multiplier)), 4)
