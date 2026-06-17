from typing import Optional

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Vocab(Base):
    __tablename__ = "vocab"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    word: Mapped[str] = mapped_column(String, nullable=False)
    reading: Mapped[str] = mapped_column(String, nullable=False)
    romaji: Mapped[Optional[str]] = mapped_column(String)
    meanings: Mapped[list] = mapped_column(JSONB, nullable=False)
    furigana: Mapped[Optional[list]] = mapped_column(JSONB)
    jlpt: Mapped[Optional[str]] = mapped_column(String)
    is_common: Mapped[Optional[bool]] = mapped_column(Boolean)
