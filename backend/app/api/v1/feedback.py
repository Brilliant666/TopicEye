from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.dependencies import get_db
from app.models.feedback import (
    UserFeedback,
    FeedbackType,
    FEEDBACK_SCORE_DELTAS,
)
from app.schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    FeedbackStatsResponse,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    data: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback for a content item.

    Prevents duplicate feedback of the same type on the same content.
    """
    # Validate feedback_type
    try:
        fb_type = FeedbackType(data.feedback_type)
    except ValueError:
        valid = ", ".join(t.value for t in FeedbackType)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid feedback_type. Must be one of: {valid}",
        )

    # Check for duplicate: same content_id + same feedback_type
    dup_check = await db.execute(
        select(UserFeedback).where(
            UserFeedback.content_id == data.content_id,
            UserFeedback.feedback_type == fb_type,
        )
    )
    if dup_check.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Feedback type '{fb_type.value}' already exists for content_id {data.content_id}",
        )

    score_delta = FEEDBACK_SCORE_DELTAS[fb_type]

    feedback = UserFeedback(
        content_id=data.content_id,
        feedback_type=fb_type,
        score_delta=score_delta,
        comment=data.comment,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)
    return feedback


@router.get("/content/{content_id}", response_model=list[FeedbackResponse])
async def get_content_feedback(
    content_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get all feedback for a specific content item."""
    result = await db.execute(
        select(UserFeedback)
        .where(UserFeedback.content_id == content_id)
        .order_by(UserFeedback.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated feedback statistics."""
    # Total count
    total_result = await db.execute(select(func.count(UserFeedback.id)))
    total = total_result.scalar() or 0

    # Count by type
    type_result = await db.execute(
        select(
            UserFeedback.feedback_type,
            func.count(UserFeedback.id),
        ).group_by(UserFeedback.feedback_type)
    )
    by_type = {str(row[0]): row[1] for row in type_result.all()}

    # Average score delta
    avg_result = await db.execute(
        select(func.avg(UserFeedback.score_delta))
    )
    avg_score = avg_result.scalar() or 0.0

    return FeedbackStatsResponse(
        total=total,
        by_type=by_type,
        avg_score_delta=round(avg_score, 2),
    )
