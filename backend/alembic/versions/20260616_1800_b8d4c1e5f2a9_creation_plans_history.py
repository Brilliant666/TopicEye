"""creation_plans history

Revision ID: b8d4c1e5f2a9
Revises: a7c3b9d2e4f6
Create Date: 2026-06-16 18:00:00

新增 creation_plans 表，持久化用户为 ContentItem 在指定平台
生成的创作方案。之前 generate_creation_plan 只返回 LLM dict
不存表，重新生成就丢历史。

字段要点：
- user_id / content_id ON DELETE CASCADE
- platform 标记平台
- content_title_snapshot 冗余存标题（内容被删时历史方案仍可展示）
- plan 字段存 LLM 完整输出（titles/structure/scenes/outline）
- error 字段保留失败方案作日志
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d4c1e5f2a9'
down_revision = 'a7c3b9d2e4f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'creation_plans',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('content_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('platform_name', sa.String(length=100), nullable=True),
        sa.Column('content_title_snapshot', sa.String(length=500), nullable=True),
        sa.Column('plan', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['content_id'], ['content_items.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_creation_plans_user', 'creation_plans', ['user_id'])
    op.create_index('ix_creation_plans_user_platform', 'creation_plans', ['user_id', 'platform'])
    op.create_index('ix_creation_plans_content', 'creation_plans', ['content_id'])


def downgrade() -> None:
    op.drop_index('ix_creation_plans_content', table_name='creation_plans')
    op.drop_index('ix_creation_plans_user_platform', table_name='creation_plans')
    op.drop_index('ix_creation_plans_user', table_name='creation_plans')
    op.drop_table('creation_plans')
