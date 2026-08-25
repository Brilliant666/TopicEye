"""PostgreSQL-owned control-plane state for the Rardar vertical POC."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RardarFindProjectJob(Base):
    __tablename__ = "rardar_find_project_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    input_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scenario: Mapped[str] = mapped_column(String(24), nullable=False, default="success")
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    state_history: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    requirement_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confirmed_requirement_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quick_candidates: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_fixture_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    explosion_artifact_revision: Mapped[str] = mapped_column(String(100), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lease_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_rardar_find_jobs_state_created", "state", "created_at"),)


class RardarAIRequest(Base):
    __tablename__ = "rardar_ai_requests"

    request_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    base_url_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reasoning_effort: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    scene: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_rardar_ai_requests_scene_created", "scene", "created_at"),)
