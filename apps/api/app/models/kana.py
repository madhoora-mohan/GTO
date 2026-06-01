from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Kana(Base):
    __tablename__ = "kana"

    character: Mapped[str] = mapped_column(String, primary_key=True)
    romaji: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    row: Mapped[Optional[str]] = mapped_column(String)
    col: Mapped[Optional[str]] = mapped_column(String)
    katakana_equivalent: Mapped[Optional[str]] = mapped_column(String)
    hiragana_equivalent: Mapped[Optional[str]] = mapped_column(String)
    mnemonic: Mapped[Optional[str]] = mapped_column(String)
    audio_url: Mapped[Optional[str]] = mapped_column(String)
    stroke_order_svg_url: Mapped[Optional[str]] = mapped_column(String)
