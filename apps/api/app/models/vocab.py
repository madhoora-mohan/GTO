from typing import Optional

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Vocab(Base):
    __tablename__ = "vocab"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    word: Mapped[str] = mapped_column(String, nullable=False)
    reading: Mapped[str] = mapped_column(String, nullable=False)
    romaji: Mapped[Optional[str]] = mapped_column(String)
    meanings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    furigana: Mapped[Optional[dict]] = mapped_column(JSONB)
    jlpt: Mapped[Optional[str]] = mapped_column(String)
    frequency: Mapped[Optional[int]] = mapped_column(Integer)
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer)
    pitch_accent: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_common: Mapped[Optional[bool]] = mapped_column(Boolean)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB)
