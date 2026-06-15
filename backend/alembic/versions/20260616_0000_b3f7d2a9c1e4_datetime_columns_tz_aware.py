"""datetime columns tz aware

Revision ID: b3f7d2a9c1e4
Revises: a9c2f4e1b7d3
Create Date: 2026-06-16 00:00:00

把所有 PG 端 DateTime 列从 TIMESTAMP WITHOUT TIME ZONE 升级为
TIMESTAMP WITH TIME ZONE. SQLite 端跳过 (底层是 TEXT, 区分 naive/aware 无意义).

现有数据按 UTC 解释: postgresql_using='<col> AT TIME ZONE \'UTC\''
依赖 backend/app/core/database.py 的 SET TIME ZONE 'UTC' connect event
保证后续写入也是 UTC.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f7d2a9c1e4'
down_revision = 'a9c2f4e1b7d3'
branch_labels = None
depends_on = None


# 71 个 DateTime 列的 (table, column) 对 (从 Base.metadata 反向提取, 完整覆盖)
DATETIME_COLUMNS = [
    ('ai_analyses', 'created_at'),
    ('analysis_jobs', 'queued_at'),
    ('analysis_jobs', 'started_at'),
    ('analysis_jobs', 'finished_at'),
    ('app_settings', 'updated_at'),
    ('categories', 'created_at'),
    ('categories', 'updated_at'),
    ('content_items', 'published_at'),
    ('content_items', 'crawled_at'),
    ('content_items', 'created_at'),
    ('content_items', 'updated_at'),
    ('content_metrics', 'snapshot_at'),
    ('daily_reports', 'generated_at'),
    ('daily_reports', 'window_start'),
    ('daily_reports', 'window_end'),
    ('daily_reports', 'cutoff_at'),
    ('daily_reports', 'created_at'),
    ('daily_reports', 'updated_at'),
    ('fanqie_books', 'crawled_at'),
    ('fanqie_categories', 'created_at'),
    ('fanqie_categories', 'updated_at'),
    ('fanqie_rank_snapshots', 'created_at'),
    ('favorite_items', 'created_at'),
    ('favorite_items', 'updated_at'),
    ('ignored_items', 'created_at'),
    ('issue_feedback', 'fixed_at'),
    ('issue_feedback', 'created_at'),
    ('issue_feedback', 'updated_at'),
    ('job_execution_logs', 'started_at'),
    ('job_execution_logs', 'finished_at'),
    ('job_execution_logs', 'created_at'),
    ('llm_call_logs', 'created_at'),
    ('llm_models', 'created_at'),
    ('llm_models', 'updated_at'),
    ('model_evaluations', 'created_at'),
    ('monthly_digests', 'created_at'),
    ('monthly_digests', 'updated_at'),
    ('mother_topics', 'created_at'),
    ('mother_topics', 'updated_at'),
    ('notifications', 'created_at'),
    ('product_updates', 'shipped_at'),
    ('product_updates', 'created_at'),
    ('product_updates', 'updated_at'),
    ('qimao_books', 'crawled_at'),
    ('scheduled_jobs', 'last_run_at'),
    ('scheduled_jobs', 'created_at'),
    ('scheduled_jobs', 'updated_at'),
    ('sources', 'last_sync_at'),
    ('sources', 'created_at'),
    ('sources', 'updated_at'),
    ('topic_groups', 'created_at'),
    ('topic_groups', 'updated_at'),
    ('topic_trends', 'created_at'),
    ('trending_items', 'fetched_at'),
    ('trending_snapshots', 'fetched_at'),
    ('user_feedback', 'created_at'),
    ('user_integrations', 'last_sync_at'),
    ('user_integrations', 'created_at'),
    ('user_integrations', 'updated_at'),
    ('user_sessions', 'expires_at'),
    ('user_sessions', 'revoked_at'),
    ('user_sessions', 'created_at'),
    ('user_sessions', 'last_seen_at'),
    ('users', 'created_at'),
    ('users', 'updated_at'),
    ('weekly_digests', 'created_at'),
    ('weekly_digests', 'updated_at'),
    ('zhihu_albums', 'created_at'),
    ('zhihu_albums', 'updated_at'),
    ('zhihu_categories', 'created_at'),
    ('zhihu_rank_snapshots', 'created_at'),
]


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        print(f"datetime tz migration: skip on {bind.dialect.name}")
        return
    insp = sa.inspect(bind)
    skipped = []
    migrated = 0
    for table, column in DATETIME_COLUMNS:
        # 防御: 跳过 PG 里不存在的表或列 (metadata 可能包含 DB 未建的旧 model)
        if not insp.has_table(table):
            skipped.append(f'{table} (table missing)')
            continue
        existing_cols = {c['name'] for c in insp.get_columns(table)}
        if column not in existing_cols:
            skipped.append(f'{table}.{column} (column missing)')
            continue
        op.alter_column(
            table, column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
        migrated += 1
    if skipped:
        print(f"datetime tz migration: migrated {migrated}, skipped {len(skipped)}: {skipped}")
    else:
        print(f"datetime tz migration: migrated {migrated}")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    insp = sa.inspect(bind)
    for table, column in DATETIME_COLUMNS:
        if not insp.has_table(table):
            continue
        existing_cols = {c['name'] for c in insp.get_columns(table)}
        if column not in existing_cols:
            continue
        op.alter_column(
            table, column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
        )
