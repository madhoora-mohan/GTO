# WHAT: The `/kana/*` HTTP routes — list and single-character lookup.
# WHY:  Keeps the HTTP shape (query params, status codes, schemas) separate
#       from the DB queries in services/kana_service.py.

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import PageParams, page_params
from app.schemas.generated import Kana, PaginatedKana
from app.services import kana_service

router = APIRouter()


@router.get("", response_model=PaginatedKana)
async def list_kana(
    type: Literal["hiragana", "katakana"] | None = Query(default=None),
    category: Literal["base", "dakuten", "handakuten", "yoon"] | None = Query(
        default=None
    ),
    page_params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
) -> PaginatedKana:
    """Public, paginated, optionally filtered by type and/or category."""
    rows, total = await kana_service.list_kana(
        db, page_params, type=type, category=category
    )
    return PaginatedKana(
        data=[Kana.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/{character}", response_model=Kana)
async def get_kana(character: str, db: AsyncSession = Depends(get_db)) -> Kana:
    """Public, single row by primary key."""
    row = await kana_service.get_kana(db, character)
    if row is None:
        raise AppError(404, "not_found", f"Kana '{character}' not found")
    return Kana.model_validate(row, from_attributes=True)
