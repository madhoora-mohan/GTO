from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KanjiVocab(Base):
    __tablename__ = "kanji_vocab"

    kanji_char: Mapped[str] = mapped_column(String, ForeignKey("kanji.character"), primary_key=True)
    vocab_id: Mapped[str] = mapped_column(String, ForeignKey("vocab.id"), primary_key=True)
