from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.generated import PracticeBatchCloze, PracticeClozeItem
from app.services.practice_service import parse_exclude
from app.services.sentence_cloze_service import get_sentence_cloze_batch

router = APIRouter()


@router.get("/sentence-cloze", response_model=PracticeBatchCloze)
async def get_sentence_cloze(
    source: Literal["kanji", "vocab"] = Query(...),
    jlpt_level: Literal["N5", "N4", "N3", "N2", "N1"] = Query(...),
    scope: Literal["exact", "and_below"] = Query(...),
    distribution: Literal["balanced", "challenge"] = Query(...),
    count: int = Query(default=20, ge=1, le=50),
    exclude: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PracticeBatchCloze:
    """Requires auth (Practice tab requires login). A stateless batch of
    sentence-cloze items, shared by the Kanji and Vocab Practice entry
    points (`source` picks which one)."""
    excluded = parse_exclude(exclude)
    items = await get_sentence_cloze_batch(
        db, source, jlpt_level, scope, distribution, count, excluded
    )
    return PracticeBatchCloze(data=[PracticeClozeItem(**item) for item in items])
