from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReadingPassage(Base):
    __tablename__ = "reading_passages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    jlpt_level: Mapped[str] = mapped_column(String, nullable=False, index=True)
    difficulty_score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Points to an R2 object, e.g. "reading/passages/1.json" — mirrors files.object_key
    content_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    # lazy="noload": we never traverse this via the ORM (reading_service
    # queries ReadingQuestion directly), and the FK's ondelete="CASCADE"
    # already handles deletion at the DB level. Without noload, Pydantic's
    # model_validate(row, from_attributes=True) in the router tries to read
    # this attribute and triggers an implicit async lazy-load outside an
    # awaited context (MissingGreenlet).
    questions: Mapped[list["ReadingQuestion"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan", lazy="noload"
    )
