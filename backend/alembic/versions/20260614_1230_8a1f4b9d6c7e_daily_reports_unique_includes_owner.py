"""daily_reports unique constraint includes owner_user_id

Revision ID: 8a1f4b9d6c7e
Revises: 5f8c2b1a3d4e
Create Date: 2026-06-14 12:30:00.000000

The old uq_daily_report_version = (report_date, edition, cutoff_at) does not
include owner_user_id, so multiple user-owned reports on the same date+edition
collide on this constraint. T2 (user-owned daily reports) needs the constraint
to be (owner_user_id, report_date, edition, cutoff_at).

In multi-column UNIQUE constraints, NULL is treated as DISTINCT — so the
single public (owner_user_id=NULL) row stays unique on its own, while
different users each get their own row. The application layer still
catches IntegrityError on the public row to handle concurrent generation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a1f4b9d6c7e'
down_revision: Union[str, None] = '5f8c2b1a3d4e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('daily_reports', schema=None) as batch_op:
        batch_op.drop_constraint('uq_daily_report_version', type_='unique')
        batch_op.create_unique_constraint(
            'uq_daily_report_version',
            ['owner_user_id', 'report_date', 'edition', 'cutoff_at'],
        )


def downgrade() -> None:
    with op.batch_alter_table('daily_reports', schema=None) as batch_op:
        batch_op.drop_constraint('uq_daily_report_version', type_='unique')
        batch_op.create_unique_constraint(
            'uq_daily_report_version',
            ['report_date', 'edition', 'cutoff_at'],
        )
