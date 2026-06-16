"""notifications per-user isolation

Revision ID: a7c3b9d2e4f6
Revises: e6b2c4d7f9a1
Create Date: 2026-06-16 17:00:00

原 notifications 表是全局共享的——所有用户看同一份通知，
is_read 也全局共享（A 标已读 = B 看见已读）。这是个严重设计 bug。

改造：
- notifications 加 target_user_id 字段（NULL=广播，非空=定向）
- 新建 notification_reads 表（per-user 复合主键）
- 清空现有 notifications 数据（修复前数据已无意义）
- 保留 is_read 字段（前端兼容），新代码不再写它

数据迁移：
- DELETE FROM notifications（旧数据被清空）
- 老 is_read 标记（已读/未读）在迁移后无意义——前端按"未读=无 NotificationRead 记录"判定
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3b9d2e4f6'
down_revision = 'e6b2c4d7f9a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 清空旧通知（避免迁移后历史"广播"消息给所有用户重新刷一遍）
    op.execute("DELETE FROM notifications")

    # 2. notifications 加 target_user_id 字段 + 索引
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('target_user_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_notif_target', ['target_user_id'])
        batch_op.create_foreign_key(
            'fk_notif_target_user', 'users', ['target_user_id'], ['id'],
            ondelete='CASCADE',
        )

    # 3. 新建 notification_reads 表
    op.create_table(
        'notification_reads',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notification_id', sa.Integer(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'notification_id'),
    )
    op.create_index('ix_notification_reads_user', 'notification_reads', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_notification_reads_user', table_name='notification_reads')
    op.drop_table('notification_reads')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_notif_target_user', type_='foreignkey')
        batch_op.drop_index('ix_notif_target')
        batch_op.drop_column('target_user_id')
