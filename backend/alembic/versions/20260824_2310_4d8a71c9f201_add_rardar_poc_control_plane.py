"""add Rardar POC control-plane tables

Revision ID: 4d8a71c9f201
Revises: c003bd551911
Create Date: 2026-08-24 23:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4d8a71c9f201"
down_revision: str | None = "c003bd551911"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rardar_find_project_jobs",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("input_mode", sa.String(length=24), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("repository_url", sa.String(length=500), nullable=True),
        sa.Column("scenario", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("state_history", sa.JSON(), nullable=False),
        sa.Column("requirement_profile", sa.JSON(), nullable=True),
        sa.Column("confirmed_requirement_profile", sa.JSON(), nullable=True),
        sa.Column("quick_candidates", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("candidate_fixture_revision", sa.String(length=100), nullable=False),
        sa.Column("explosion_artifact_revision", sa.String(length=100), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("retry_state", sa.String(length=40), nullable=True),
        sa.Column("lease_id", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index("ix_rardar_find_project_jobs_state", "rardar_find_project_jobs", ["state"])
    op.create_index("ix_rardar_find_project_jobs_lease_id", "rardar_find_project_jobs", ["lease_id"])
    op.create_index(
        "ix_rardar_find_jobs_state_created",
        "rardar_find_project_jobs",
        ["state", "created_at"],
    )

    op.create_table(
        "rardar_ai_requests",
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("base_url_identifier", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=16), nullable=False),
        sa.Column("scene", sa.String(length=80), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result_state", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index("ix_rardar_ai_requests_provider", "rardar_ai_requests", ["provider"])
    op.create_index("ix_rardar_ai_requests_model", "rardar_ai_requests", ["model"])
    op.create_index("ix_rardar_ai_requests_reasoning_effort", "rardar_ai_requests", ["reasoning_effort"])
    op.create_index("ix_rardar_ai_requests_scene", "rardar_ai_requests", ["scene"])
    op.create_index("ix_rardar_ai_requests_input_hash", "rardar_ai_requests", ["input_hash"])
    op.create_index("ix_rardar_ai_requests_result_state", "rardar_ai_requests", ["result_state"])
    op.create_index(
        "ix_rardar_ai_requests_scene_created",
        "rardar_ai_requests",
        ["scene", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rardar_ai_requests_scene_created", table_name="rardar_ai_requests")
    op.drop_index("ix_rardar_ai_requests_result_state", table_name="rardar_ai_requests")
    op.drop_index("ix_rardar_ai_requests_input_hash", table_name="rardar_ai_requests")
    op.drop_index("ix_rardar_ai_requests_scene", table_name="rardar_ai_requests")
    op.drop_index("ix_rardar_ai_requests_reasoning_effort", table_name="rardar_ai_requests")
    op.drop_index("ix_rardar_ai_requests_model", table_name="rardar_ai_requests")
    op.drop_index("ix_rardar_ai_requests_provider", table_name="rardar_ai_requests")
    op.drop_table("rardar_ai_requests")
    op.drop_index("ix_rardar_find_jobs_state_created", table_name="rardar_find_project_jobs")
    op.drop_index("ix_rardar_find_project_jobs_lease_id", table_name="rardar_find_project_jobs")
    op.drop_index("ix_rardar_find_project_jobs_state", table_name="rardar_find_project_jobs")
    op.drop_table("rardar_find_project_jobs")
