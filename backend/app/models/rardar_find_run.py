"""Private Find business records, separate from logs, profiles and budgets."""

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RardarFindRun(Base):
    __tablename__ = "rardar_find_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_rardar_find_user_key"),
        Index("ix_rardar_find_user_created", "user_id", "created_at"),
        CheckConstraint(
            "request_limit >= 0 AND requests_used >= 0 AND requests_used <= request_limit", name="ck_find_run_requests"
        ),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    requirement_summary: Mapped[str] = mapped_column(String(160), nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    result_payload: Mapped[dict | None] = mapped_column(JSON)
    result_schema_version: Mapped[str] = mapped_column(String(64), nullable=False, default="rardar-find-run-v1")
    audit_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(100))
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_token: Mapped[str | None] = mapped_column(String(36))
    execution_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
