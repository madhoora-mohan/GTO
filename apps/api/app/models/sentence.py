from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Sentence(Base):
    __tablename__ = "sentences"
    __table_args__ = (
        # Trigram index for fuzzy/substring search on Japanese text.
        # Created directly via raw SQL (not an Alembic migration) — declared
        # here so SQLAlchemy metadata matches the actual DB schema and
        # `alembic check`/autogenerate stop reporting it as drift.
        Index(
            "ix_sentences_japanese_trgm",
            "japanese",
            postgresql_using="gin",
            postgresql_ops={"japanese": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    japanese: Mapped[str] = mapped_column(Text, nullable=False)
    english: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, default="tatoeba", nullable=False)
