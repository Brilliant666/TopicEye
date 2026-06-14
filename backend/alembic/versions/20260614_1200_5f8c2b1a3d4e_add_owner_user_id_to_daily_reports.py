"""add owner_user_id to daily_reports

Revision ID: 5f8c2b1a3d4e
Revises: 722e2afdc4b9
Create Date: 2026-06-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f8c2b1a3d4e'
down_revision: Union[str, None] = '722e2afdc4b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # daily_reports: 加 owner_user_id（nullable，NULL=全局公共日报；非 NULL=用户专属）
    # 唯一约束 uq_daily_report_version 保持 (report_date, edition, cutoff_at) 不变 —
    # 公共行/用户行的去重靠应用层 owner_user_id IS NULL 等价（SQLAlchemy is_(None) 兼容），
    # 避免 SQLite/PG 在多列 unique 中 NULL 视为 distinct 导致的重复公共日报问题。
    with op.batch_alter_table('daily_reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'owner_user_id', sa.Integer(), nullable=True,
            comment='NULL=全局公共日报；非 NULL=用户专属日报',
        ))
        batch_op.create_index('ix_daily_reports_owner', ['owner_user_id'], unique=False)
        batch_op.create_index('ix_daily_reports_owner_date', ['owner_user_id', 'report_date'], unique=False)
        batch_op.create_foreign_key(
            'fk_daily_reports_owner_user_id', 'users',
            ['owner_user_id'], ['id'], ondelete='CASCADE',
        )

    # 历史日报 owner_user_id 保持 NULL（自动归为公共），无需回填


def downgrade() -> None:
    with op.batch_alter_table('daily_reports', schema=None) as batch_op:
        batch_op.drop_constraint('fk_daily_reports_owner_user_id', type_='foreignkey')
        batch_op.drop_index('ix_daily_reports_owner_date')
        batch_op.drop_index('ix_daily_reports_owner')
        batch_op.drop_column('owner_user_id')
