from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.sentence import Sentence
from app.services.jlpt import JLPT_RANK, jlpt_order

_SENTENCE_JLPT_ORDER = jlpt_order(Sentence.jlpt)


async def list_sentences(
    db: AsyncSession,
    page_params: PageParams,
    jlpt: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
    jlpt_max: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
    search: str | None = None,
) -> tuple[list[Sentence], int]:
    """Return (rows, total) for GET /sentences, applying optional jlpt,
    jlpt_max, search filters. jlpt and jlpt_max are mutually exclusive
    (caller must validate)."""
    stmt = select(Sentence)
    count_stmt = select(func.count()).select_from(Sentence)

    if jlpt is not None:
        stmt = stmt.where(Sentence.jlpt == jlpt)
        count_stmt = count_stmt.where(Sentence.jlpt == jlpt)
    elif jlpt_max is not None:
        stmt = stmt.where(_SENTENCE_JLPT_ORDER <= JLPT_RANK[jlpt_max])
        count_stmt = count_stmt.where(_SENTENCE_JLPT_ORDER <= JLPT_RANK[jlpt_max])
    if search is not None:
        condition = Sentence.japanese.like(f"%{search}%")
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(_SENTENCE_JLPT_ORDER, Sentence.id.asc())
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_sentence(db: AsyncSession, sentence_id: int) -> Sentence | None:
    """Return the Sentence row for 'sentence_id', or None if it does not exist"""
    return await db.get(Sentence, sentence_id)
