"""drop_audio_url_columns

Revision ID: 66c2aefbe3ce
Revises: 82fd3377c68c
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66c2aefbe3ce'
down_revision: Union[str, Sequence[str], None] = '82fd3377c68c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Reverts the columns added in 82fd3377c68c — audio strategy was finalized
    as kana-only (Wikimedia Commons), so kanji/vocab/sentence audio columns
    are dropped. See docs/audio-implementation-intervention.md.
    """
    op.drop_column('vocab', 'audio_url')
    op.drop_column('sentences', 'audio_url')
    op.drop_column('kanji', 'kunyomi_audio_url')
    op.drop_column('kanji', 'onyomi_audio_url')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('kanji', sa.Column('onyomi_audio_url', sa.Text(), nullable=True))
    op.add_column('kanji', sa.Column('kunyomi_audio_url', sa.Text(), nullable=True))
    op.add_column('sentences', sa.Column('audio_url', sa.Text(), nullable=True))
    op.add_column('vocab', sa.Column('audio_url', sa.Text(), nullable=True))
