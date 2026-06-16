from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KanjiVocab(Base):
    __tablename__ = "kanji_vocab"

    kanji_char: Mapped[str] = mapped_column(String, ForeignKey("kanji.character"), primary_key=True)
    vocab_id: Mapped[str] = mapped_column(String, ForeignKey("vocab.id"), primary_key=True)
    reading_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "on", "kun", or NULL if the reading could not be resolved
