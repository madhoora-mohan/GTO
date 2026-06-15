from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.sentence import Sentence


async def list_sentences(
    db: AsyncSession,
    page_params: PageParams,
    search: str | None = None,
) -> tuple[list[Sentence], int]:
    """Return (rows, total) for GET /sentences, applying optional search filter."""
    stmt = select(Sentence)
    count_stmt = select(func.count()).select_from(Sentence)

    if search is not None:
        condition = Sentence.japanese.like(f"%{search}%")
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Sentence.id.asc())
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_sentence(db: AsyncSession, sentence_id: int) -> Sentence | None:
    """Return the Sentence row for 'sentence_id', or None if it does not exist"""
    return await db.get(Sentence, sentence_id)
