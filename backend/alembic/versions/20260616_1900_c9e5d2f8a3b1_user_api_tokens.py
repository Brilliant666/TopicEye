"""user api tokens

Revision ID: c9e5d2f8a3b1
Revises: b8d4c1e5f2a9
Create Date: 2026-06-16 19:00:00

新增 user_api_tokens 表，让用户能创建个人 access token
用于脚本/CI 调用 API（区别于浏览器登录会话 UserSession）。

特性：
- 命名 token（用户可读名字，如 'CI 脚本'）
- 可选过期时间
- 支持撤销（revoked_at）
- token_hash 唯一 + 索引，active 复合索引（token_hash + revoked_at）
- token_prefix 仅存前 8 位，UI 上识别用，不暴露完整 hash
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e5d2f8a3b1'
down_revision = 'b8d4c1e5f2a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_api_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('token_prefix', sa.String(length=16), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('token_hash', name='uq_user_api_tokens_token_hash'),
    )
    op.create_index(
        'ix_user_api_tokens_user_active', 'user_api_tokens', ['user_id', 'revoked_at'],
    )
    op.create_index(
        'ix_user_api_tokens_token_active', 'user_api_tokens', ['token_hash', 'revoked_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_user_api_tokens_token_active', table_name='user_api_tokens')
    op.drop_index('ix_user_api_tokens_user_active', table_name='user_api_tokens')
    op.drop_table('user_api_tokens')
