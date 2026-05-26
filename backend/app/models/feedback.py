from __future__ import annotations
from typing import Optional
import enum
from datetime import datetime
from sqlalchemy import Integer, Float, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class FeedbackType(str, enum.Enum):
    like = "like"
    dislike = "dislike"
    skip = "skip"
    not_relevant = "not_relevant"
    outdated = "outdated"
    great_pick = "great_pick"


# Mapping from feedback type to score delta
FEEDBACK_SCORE_DELTAS: dict[FeedbackType, float] = {
    FeedbackType.like: +10.0,
    FeedbackType.dislike: -15.0,
    FeedbackType.skip: -5.0,
    FeedbackType.not_relevant: -20.0,
    FeedbackType.outdated: -10.0,
    FeedbackType.great_pick: +20.0,
}


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    feedback_type: Mapped[str] = mapped_column(
        Enum(FeedbackType), nullable=False
    )
    score_delta: Mapped[float] = mapped_column(Float, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
