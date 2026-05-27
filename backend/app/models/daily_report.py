"""
Daily Report model — AI-generated daily briefing for creators.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("report_date", "edition", "cutoff_at", name="uq_daily_report_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    weekday: Mapped[str] = mapped_column(String(10), nullable=False)  # 周一~周日
    edition: Mapped[str] = mapped_column(String(20), default="snapshot", nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    source_scope: Mapped[str] = mapped_column(String(20), default="curated", nullable=False)
    source_item_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Overview
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    takeaway: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Keywords (JSON array string)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Trends (JSON array of {title, desc, color})
    trends: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Top picks (JSON array of {title, reason, score, platforms})
    top_picks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Platform tips (JSON object {platform: [tips]})
    platform_tips: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Stats
    topic_count: Mapped[int] = mapped_column(Integer, default=0)
    content_count: Mapped[int] = mapped_column(Integer, default=0)
    analyzed_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING / GENERATING / DONE / ERROR

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
