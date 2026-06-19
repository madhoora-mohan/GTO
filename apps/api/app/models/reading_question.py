from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReadingQuestion(Base):
    __tablename__ = "reading_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    passage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reading_passages.id", ondelete="CASCADE"), nullable=False
    )
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Points to an R2 object, e.g. "reading/questions/1.json"
    content_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    passage: Mapped["ReadingPassage"] = relationship(back_populates="questions")
