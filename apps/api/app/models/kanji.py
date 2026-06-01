from typing import Optional

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Kanji(Base):
    __tablename__ = "kanji"

    character: Mapped[str] = mapped_column(String, primary_key=True)
    unicode_hex: Mapped[str] = mapped_column(String, nullable=False)
    meanings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    onyomi: Mapped[Optional[dict]] = mapped_column(JSONB)
    kunyomi: Mapped[Optional[dict]] = mapped_column(JSONB)
    nanori: Mapped[Optional[dict]] = mapped_column(JSONB)
    jlpt: Mapped[Optional[str]] = mapped_column(String)
    grade: Mapped[Optional[int]] = mapped_column(Integer)
    stroke_count: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency: Mapped[Optional[int]] = mapped_column(Integer)
    classical_radical_number: Mapped[Optional[int]] = mapped_column(Integer)
    classical_radical_char: Mapped[Optional[str]] = mapped_column(String)
    stroke_order_svg_url: Mapped[Optional[str]] = mapped_column(String)
    mnemonic: Mapped[Optional[str]] = mapped_column(Text)
