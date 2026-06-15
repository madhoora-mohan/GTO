from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.component import Component


async def list_components(
    db: AsyncSession, page_params: PageParams
) -> tuple[list[Component], int]:
    """Return (rows, total) for GET /components, no filters."""
    total = (await db.execute(select(func.count()).select_from(Component))).scalar_one()

    stmt = (
        select(Component)
        .order_by(Component.stroke_count.asc(), Component.id.asc())
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_component(db: AsyncSession, component_id: int) -> Component | None:
    """Return the Component row for 'component_id', or None if it does not exist"""
    return await db.get(Component, component_id)
