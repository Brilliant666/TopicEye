from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enum_types import value_enum


class IssueFeedbackSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IssueFeedbackStatus(str, enum.Enum):
    open = "open"
    triaged = "triaged"
    in_progress = "in_progress"
    fixed = "fixed"
    closed = "closed"


class ProductUpdateKind(str, enum.Enum):
    roadmap = "roadmap"
    release = "release"
    fix = "fix"
    improvement = "improvement"


class ProductUpdateStatus(str, enum.Enum):
    planned = "planned"
    in_progress = "in_progress"
    shipped = "shipped"


class IssueFeedback(Base):
    __tablename__ = "issue_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    area: Mapped[str] = mapped_column(String(80), nullable=False, default="general")
    severity: Mapped[str] = mapped_column(value_enum(IssueFeedbackSeverity), nullable=False, default=IssueFeedbackSeverity.medium)
    status: Mapped[str] = mapped_column(value_enum(IssueFeedbackStatus), nullable=False, default=IssueFeedbackStatus.open)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fixed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")

    __table_args__ = (
        Index("ix_issue_feedback_user_created", "user_id", "created_at"),
        Index("ix_issue_feedback_status_created", "status", "created_at"),
        Index("ix_issue_feedback_severity_created", "severity", "created_at"),
    )


class ProductUpdate(Base):
    __tablename__ = "product_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(value_enum(ProductUpdateKind), nullable=False, default=ProductUpdateKind.roadmap)
    status: Mapped[str] = mapped_column(value_enum(ProductUpdateStatus), nullable=False, default=ProductUpdateStatus.planned)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = relationship("User")

    __table_args__ = (
        Index("ix_product_updates_kind_status", "kind", "status"),
        Index("ix_product_updates_status_created", "status", "created_at"),
        Index("ix_product_updates_shipped_at", "shipped_at"),
    )
