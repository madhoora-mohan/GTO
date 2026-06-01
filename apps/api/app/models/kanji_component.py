from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KanjiComponent(Base):
    __tablename__ = "kanji_component"

    kanji_char: Mapped[str] = mapped_column(String, ForeignKey("kanji.character"), primary_key=True)
    component_id: Mapped[int] = mapped_column(Integer, ForeignKey("components.id"), primary_key=True)
    position: Mapped[Optional[int]] = mapped_column(Integer)
