"""add kanji_sentence sentence_id index

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-06-17 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f6a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'e5f6a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_kanji_sentence_sentence_id',
        'kanji_sentence',
        ['sentence_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_kanji_sentence_sentence_id', table_name='kanji_sentence')
