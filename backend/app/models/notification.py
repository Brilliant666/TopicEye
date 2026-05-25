"""
站内通知模型。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    """站内通知。"""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # success / error / warning / info
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # fanqie_sync / daily_report / weekly_digest / system
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_notif_read", "is_read"),
        Index("ix_notif_cat", "category"),
    )
