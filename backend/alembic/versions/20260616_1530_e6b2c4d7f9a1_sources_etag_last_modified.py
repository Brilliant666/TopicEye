"""sources etag last_modified

Revision ID: e6b2c4d7f9a1
Revises: d5e9a2b3c4f5
Create Date: 2026-06-16 15:30:00

为信源加 HTTP 条件请求状态：保存上次响应的 ETag / Last-Modified，
下次抓取时通过 If-None-Match / If-Modified-Since 头告诉服务器
"如果没变返回 304"——节省带宽 + 减少解析开销。

复用 ContentItem 同款 batch_alter_table 兼容 SQLite。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6b2c4d7f9a1'
down_revision = 'd5e9a2b3c4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('etag', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('last_modified', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('last_modified')
        batch_op.drop_column('etag')
