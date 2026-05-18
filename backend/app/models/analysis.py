from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlalchemy import Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AiAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    hot_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    freshness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    creator_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    viral_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    platform_fit: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    recommended_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_points: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    audience_emotion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    creator_angles: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    title_suggestions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    outline_suggestions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    xiaohongshu_plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    short_video_plan: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    risk_notes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # ── Curation fields ──
    curation_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)          # multi-tag: ["模型","产品"]
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # AI 生成口语化推荐理由
    source_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=50.0)
    info_density: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=50.0)
    actionability: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=50.0)
    # ── Round-2 enrichment fields ──
    enrichment_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="pending")  # pending|completed|error
    enrichment: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # background/related_angles/why_matters/creator_tips
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    content: Mapped["ContentItem"] = relationship(back_populates="analyses")
