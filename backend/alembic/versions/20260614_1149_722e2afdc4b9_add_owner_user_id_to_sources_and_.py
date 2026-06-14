"""add owner_user_id to sources and content_items

Revision ID: 722e2afdc4b9
Revises: e287169df13c
Create Date: 2026-06-14 11:49:17.328278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '722e2afdc4b9'
down_revision: Union[str, None] = 'e287169df13c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sources: 加 owner_user_id（nullable，NULL=公共）+ scope（NOT NULL，server_default='system' 保证老行有值）
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('scope', sa.String(length=20), nullable=False, server_default='system'))
        batch_op.create_index('ix_sources_owner', ['owner_user_id'], unique=False)
        batch_op.create_index('ix_sources_owner_enabled', ['owner_user_id', 'enabled'], unique=False)
        batch_op.create_foreign_key('fk_sources_owner_user_id', 'users', ['owner_user_id'], ['id'], ondelete='CASCADE')

    # content_items: 加冗余 owner_user_id（nullable，NULL=公共内容池）
    with op.batch_alter_table('content_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True, comment='冗余 source.owner_user_id；NULL=公共内容池'))
        batch_op.create_index('ix_content_items_owner', ['owner_user_id'], unique=False)
        batch_op.create_index('ix_content_items_owner_status', ['owner_user_id', 'status'], unique=False)

    # 回填：把 content_items.owner_user_id 从其 source 冗余过来（source_id 已失效的行保持 NULL=公共）
    op.execute("""
        UPDATE content_items
        SET owner_user_id = (
            SELECT s.owner_user_id FROM sources s WHERE s.id = content_items.source_id
        )
        WHERE owner_user_id IS NULL
          AND source_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM sources s WHERE s.id = content_items.source_id AND s.owner_user_id IS NOT NULL)
    """)


def downgrade() -> None:
    with op.batch_alter_table('content_items', schema=None) as batch_op:
        batch_op.drop_index('ix_content_items_owner_status')
        batch_op.drop_index('ix_content_items_owner')
        batch_op.drop_column('owner_user_id')

    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sources_owner_user_id', type_='foreignkey')
        batch_op.drop_index('ix_sources_owner_enabled')
        batch_op.drop_index('ix_sources_owner')
        batch_op.drop_column('scope')
        batch_op.drop_column('owner_user_id')
