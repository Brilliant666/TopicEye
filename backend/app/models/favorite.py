from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enum_types import value_enum


class FavoriteTargetType(str, enum.Enum):
    CONTENT = "content"
    BOOK = "book"
    SOURCE = "source"
    TREND = "trend"
    AUTHOR = "author"
    TOPIC_GROUP = "topic_group"


class FavoriteStatus(str, enum.Enum):
    INBOX = "inbox"
    RESEARCHING = "researching"
    DRAFTING = "drafting"
    ARCHIVED = "archived"


class FavoriteItem(Base):
    __tablename__ = "favorite_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(value_enum(FavoriteTargetType), nullable=False)
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    cover_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    collection_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(value_enum(FavoriteStatus), nullable=False, default=FavoriteStatus.INBOX)
    snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("target_type", "target_key", name="uq_favorite_target"),
        Index("ix_favorite_items_type_created", "target_type", "created_at"),
        Index("ix_favorite_items_status_created", "status", "created_at"),
    )
