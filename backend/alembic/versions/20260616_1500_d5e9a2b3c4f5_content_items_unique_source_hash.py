"""content_items unique on (source_id, content_hash)

Revision ID: d5e9a2b3c4f5
Revises: c4e8f1a2b9d3
Create Date: 2026-06-16 15:00:00

DB 层并发安全兜底。content_items 之前只有非唯一索引
ix_content_items_content_hash，应用层用 SELECT IN 预过滤。
在多 worker / 跨 source 抓取同时插入同一 (source_id, content_hash)
时，应用层去重有竞态窗口——会插入重复行。

加 UNIQUE 约束 (source_id, content_hash) + 配套 pipeline 改用
dialect.insert + on_conflict_do_nothing，让重复入库在 DB 层
被原子拒绝。

迁移步骤：
1. 防御性去重：保留 (source_id, content_hash) 分组中 id 最小的那行
   （NULL content_hash 不参与，依赖 PG/SQLite 的 NULL DISTINCT 行为）
2. 删旧非唯一索引（UNIQUE 约束自带索引）
3. 加 UNIQUE 约束
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e9a2b3c4f5'
down_revision = 'c4e8f1a2b9d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 防御性去重：保留 (source_id, content_hash) 分组里 id 最小的那行
    op.execute(
        """
        DELETE FROM content_items
        WHERE id NOT IN (
            SELECT MIN(id) FROM content_items
            WHERE content_hash IS NOT NULL
            GROUP BY source_id, content_hash
        )
        AND content_hash IS NOT NULL
        """
    )

    # 2. 删旧非唯一索引（UNIQUE 约束自带索引）
    with op.batch_alter_table('content_items', schema=None) as batch_op:
        batch_op.drop_index('ix_content_items_content_hash')

    # 3. 加 UNIQUE 约束
    with op.batch_alter_table('content_items', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_content_items_source_hash',
            ['source_id', 'content_hash'],
        )


def downgrade() -> None:
    with op.batch_alter_table('content_items', schema=None) as batch_op:
        batch_op.drop_constraint('uq_content_items_source_hash', type_='unique')
        batch_op.create_index(
            batch_op.f('ix_content_items_content_hash'),
            ['content_hash'],
            unique=False,
        )
