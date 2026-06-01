from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VocabSentence(Base):
    __tablename__ = "vocab_sentence"

    vocab_id: Mapped[str] = mapped_column(String, ForeignKey("vocab.id"), primary_key=True)
    sentence_id: Mapped[int] = mapped_column(Integer, ForeignKey("sentences.id"), primary_key=True)
