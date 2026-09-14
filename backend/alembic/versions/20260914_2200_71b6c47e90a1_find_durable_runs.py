"""Persist private Find results and request ownership.

Revision ID: 71b6c47e90a1
Revises: c003bd551911
"""

import sqlalchemy as sa

from alembic import op

revision = "71b6c47e90a1"
down_revision = "c003bd551911"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rardar_find_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("requirement_summary", sa.String(160), nullable=False),
        sa.Column("repository_url", sa.String(300)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("result_payload", sa.JSON()),
        sa.Column("result_schema_version", sa.String(64), nullable=False),
        sa.Column("audit_metadata", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("request_limit", sa.Integer(), nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.String(36)),
        sa.Column("execution_deadline", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_rardar_find_user_key"),
        sa.CheckConstraint(
            "request_limit >= 0 AND requests_used >= 0 AND requests_used <= request_limit", name="ck_find_run_requests"
        ),
    )
    op.create_index("ix_rardar_find_user_created", "rardar_find_runs", ["user_id", "created_at"])


def downgrade():
    # Operators must back up private results before an explicitly chosen schema rollback.
    op.drop_index("ix_rardar_find_user_created", table_name="rardar_find_runs")
    op.drop_table("rardar_find_runs")
