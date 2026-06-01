from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KanjiSentence(Base):
    __tablename__ = "kanji_sentence"

    kanji_char: Mapped[str] = mapped_column(String, ForeignKey("kanji.character"), primary_key=True)
    sentence_id: Mapped[int] = mapped_column(Integer, ForeignKey("sentences.id"), primary_key=True)
