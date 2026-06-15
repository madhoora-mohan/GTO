from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import PageParams, page_params
from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.generated import (
    Component,
    Kanji,
    MnemonicUpdateInput,
    MnemonicUpdateResponse,
    PaginatedKanji,
    Sentence,
)
from app.services import kanji_service

router = APIRouter()


@router.get("", response_model=PaginatedKanji)
async def list_kanji(
    jlpt: Literal["N1", "N2", "N3", "N4", "N5"] | None = Query(default=None),
    jlpt_max: Literal["N1", "N2", "N3", "N4", "N5"] | None = Query(default=None),
    grade: int | None = Query(default=None),
    stroke_count: int | None = Query(default=None),
    page_params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
) -> PaginatedKanji:
    """Public, paginated, optionally filtered by jlpt/jlpt_max, grade, and/or stroke_count"""
    if jlpt is not None and jlpt_max is not None:
        raise AppError(422, "validation_error", "jlpt and jlpt_max are mutually exclusive")

    rows, total = await kanji_service.list_kanji(
        db, page_params, jlpt=jlpt, jlpt_max=jlpt_max, grade=grade, stroke_count=stroke_count
    )
    return PaginatedKanji(
        data=[Kanji.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/{character}", response_model=Kanji)
async def get_kanji(
    character: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Kanji:
    """Requires auth. Returns the kanji with its components, up to 10
    example sentences (ordered by ID), and the user's mnemonic override."""
    row = await kanji_service.get_kanji(db, character)
    if row is None:
        raise AppError(404, "not_found", f"Kanji '{character}' not found")

    components = await kanji_service.get_components(db, character)
    sentences = await kanji_service.get_sentences(db, character)
    user_mnemonic = await kanji_service.get_user_mnemonic(db, user.id, character)

    kanji = Kanji.model_validate(row, from_attributes=True)
    return kanji.model_copy(
        update={
            "components": [Component.model_validate(c, from_attributes=True) for c in components],
            "sentences": [Sentence.model_validate(s, from_attributes=True) for s in sentences],
            "user_mnemonic": user_mnemonic,
        }
    )


@router.patch("/{character}/mnemonic", response_model=MnemonicUpdateResponse)
async def update_kanji_mnemonic(
    character: str,
    body: MnemonicUpdateInput,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MnemonicUpdateResponse:
    """Requires auth. Set the user's mnemonic override for this kanji, or
    clear it (revert to the LLM default) by sending an empty string."""
    row = await kanji_service.get_kanji(db, character)
    if row is None:
        raise AppError(404, "not_found", f"Kanji '{character}' not found")

    user_mnemonic = await kanji_service.set_user_mnemonic(db, user.id, character, body.mnemonic)
    return MnemonicUpdateResponse(character=character, user_mnemonic=user_mnemonic)
