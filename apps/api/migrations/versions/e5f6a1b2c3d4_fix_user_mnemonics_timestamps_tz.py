"""fix user_mnemonics timestamps tz

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-06-17 00:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a1b2c3d4'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'user_mnemonics', 'created_at',
        type_=sa.TIMESTAMP(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'user_mnemonics', 'updated_at',
        type_=sa.TIMESTAMP(timezone=True),
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        'user_mnemonics', 'created_at',
        type_=sa.TIMESTAMP(timezone=False),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'user_mnemonics', 'updated_at',
        type_=sa.TIMESTAMP(timezone=False),
        postgresql_using="updated_at AT TIME ZONE 'UTC'",
    )
