from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.reading_passage import ReadingPassage
from app.models.reading_question import ReadingQuestion
from app.services.r2_service import get_json


async def list_passages(
    db: AsyncSession,
    page_params: PageParams,
    jlpt_level: Literal["N5", "N4", "N3", "N2", "N1"] | None = None,
) -> tuple[list[ReadingPassage], int]:
    """Return (rows, total) for GET /reading/passages. Metadata only —
    callers must NOT fetch R2 content here; that's detail-endpoint only."""
    stmt = select(ReadingPassage)
    count_stmt = select(func.count()).select_from(ReadingPassage)

    if jlpt_level is not None:
        stmt = stmt.where(ReadingPassage.jlpt_level == jlpt_level)
        count_stmt = count_stmt.where(ReadingPassage.jlpt_level == jlpt_level)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(ReadingPassage.id.asc())
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_passage(db: AsyncSession, passage_id: int) -> ReadingPassage | None:
    """Return the ReadingPassage row for 'passage_id', or None if it does not exist"""
    return await db.get(ReadingPassage, passage_id)


async def get_questions(db: AsyncSession, passage_id: int) -> list[ReadingQuestion]:
    """All questions for this passage, ordered by question_order."""
    stmt = (
        select(ReadingQuestion)
        .where(ReadingQuestion.passage_id == passage_id)
        .order_by(ReadingQuestion.question_order.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


def get_passage_content(content_key: str) -> dict:
    """Fetch {passage_text, furigana_segments, english_translation} from R2."""
    return get_json(content_key)


def get_question_content(content_key: str) -> dict:
    """Fetch {question_text, options, correct_answer, explanation} from R2."""
    return get_json(content_key)
