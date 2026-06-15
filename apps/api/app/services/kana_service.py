# WHAT: DB queries backing the /kana routes.
# WHY:  Keeps routers/kana.py thin — it parses the request and shapes the
#       response, this module talks to the database.

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.kana import Kana


async def list_kana(
    db: AsyncSession,
    page_params: PageParams,
    type: str | None = None,
    category: str | None = None,
) -> tuple[list[Kana], int]:
    """Return (rows, total) for GET /kana, applying optional type/category filters."""
    stmt = select(Kana)
    count_stmt = select(func.count()).select_from(Kana)

    if type is not None:
        stmt = stmt.where(Kana.type == type)
        count_stmt = count_stmt.where(Kana.type == type)
    if category is not None:
        stmt = stmt.where(Kana.category == category)
        count_stmt = count_stmt.where(Kana.category == category)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Kana.character.asc())
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_kana(db: AsyncSession, character: str) -> Kana | None:
    """Return the Kana row for `character`, or None if it doesn't exist."""
    return await db.get(Kana, character)
