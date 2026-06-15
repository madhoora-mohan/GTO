from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import PageParams, page_params
from app.schemas.generated import PaginatedVocab, Sentence, Vocab
from app.services import vocab_service

router = APIRouter()


@router.get("", response_model=PaginatedVocab)
async def list_vocab(
    jlpt: Literal["N1", "N2", "N3", "N4", "N5"] | None = Query(default=None),
    jlpt_max: Literal["N1", "N2", "N3", "N4", "N5"] | None = Query(default=None),
    is_common: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page_params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
) -> PaginatedVocab:
    """Public, paginated, optionally filtered by jlpt/jlpt_max/is_common and searched by word/reading"""
    if jlpt is not None and jlpt_max is not None:
        raise AppError(422, "validation_error", "jlpt and jlpt_max are mutually exclusive")

    rows, total = await vocab_service.list_vocab(
        db, page_params, jlpt=jlpt, jlpt_max=jlpt_max, is_common=is_common, search=search
    )
    return PaginatedVocab(
        data=[Vocab.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/{vocab_id}", response_model=Vocab)
async def get_vocab(
    vocab_id: str,
    db: AsyncSession = Depends(get_db),
) -> Vocab:
    """Public. Returns the vocab entry with up to 10 example sentences (ordered by ID)."""
    row = await vocab_service.get_vocab(db, vocab_id)
    if row is None:
        raise AppError(404, "not_found", f"Vocab '{vocab_id}' not found")

    sentences = await vocab_service.get_sentences(db, vocab_id)

    vocab = Vocab.model_validate(row, from_attributes=True)
    return vocab.model_copy(
        update={
            "sentences": [Sentence.model_validate(s, from_attributes=True) for s in sentences],
        }
    )
