"""drop vocab_sentence

Revision ID: a1b2c3d4e5f6
Revises: c17d67f66e28
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c17d67f66e28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('vocab_sentence')


def downgrade() -> None:
    op.create_table(
        'vocab_sentence',
        sa.Column('vocab_id', sa.String(), nullable=False),
        sa.Column('sentence_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['sentence_id'], ['sentences.id']),
        sa.ForeignKeyConstraint(['vocab_id'], ['vocab.id']),
        sa.PrimaryKeyConstraint('vocab_id', 'sentence_id'),
    )
