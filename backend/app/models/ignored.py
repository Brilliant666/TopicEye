from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class IgnoredItem(Base):
    __tablename__ = "ignored_items"
    __table_args__ = (UniqueConstraint("content_id", name="uq_ignored_content"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="not_interested")  # not_interested | seen | irrelevant
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    content: Mapped[Optional["ContentItem"]] = relationship("ContentItem")
