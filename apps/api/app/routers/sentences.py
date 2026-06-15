from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import PageParams, page_params
from app.schemas.generated import PaginatedSentence, Sentence
from app.services import sentence_service

router = APIRouter()


@router.get("", response_model=PaginatedSentence)
async def list_sentences(
    jlpt: Literal["N1", "N2", "N3", "N4", "N5"] | None = Query(default=None),
    jlpt_max: Literal["N1", "N2", "N3", "N4", "N5"] | None = Query(default=None),
    search: str | None = Query(default=None),
    page_params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
) -> PaginatedSentence:
    """Public, paginated, optionally filtered by jlpt/jlpt_max and searched by Japanese text"""
    if jlpt is not None and jlpt_max is not None:
        raise AppError(422, "validation_error", "jlpt and jlpt_max are mutually exclusive")

    rows, total = await sentence_service.list_sentences(
        db, page_params, jlpt=jlpt, jlpt_max=jlpt_max, search=search
    )
    return PaginatedSentence(
        data=[Sentence.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/{sentence_id}", response_model=Sentence)
async def get_sentence(
    sentence_id: int,
    db: AsyncSession = Depends(get_db),
) -> Sentence:
    """Public. Returns a single example sentence."""
    row = await sentence_service.get_sentence(db, sentence_id)
    if row is None:
        raise AppError(404, "not_found", f"Sentence '{sentence_id}' not found")
    return Sentence.model_validate(row, from_attributes=True)
