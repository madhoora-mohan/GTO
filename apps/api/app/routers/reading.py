from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.pagination import PageParams, page_params
from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.generated import PaginatedReadingPassage, ReadingPassage, ReadingQuestion
from app.services import reading_service

router = APIRouter()


@router.get("/passages", response_model=PaginatedReadingPassage)
async def list_passages(
    jlpt_level: Literal["N5", "N4", "N3", "N2", "N1"] | None = Query(default=None),
    page_params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
) -> PaginatedReadingPassage:
    """Public, paginated, optionally filtered by jlpt_level. Metadata only —
    passage_text/furigana_segments/english_translation/questions are
    omitted here to avoid an R2 fetch per row; see GET /{id} for full content."""
    rows, total = await reading_service.list_passages(db, page_params, jlpt_level=jlpt_level)
    return PaginatedReadingPassage(
        data=[ReadingPassage.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )


@router.get("/passages/{passage_id}", response_model=ReadingPassage)
async def get_passage(
    passage_id: int,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadingPassage:
    """Requires auth. Fetches passage content from R2 and all questions (with
    their own content fetched from R2), ordered by question_order."""
    row = await reading_service.get_passage(db, passage_id)
    if row is None:
        raise AppError(404, "not_found", f"Reading passage '{passage_id}' not found")

    content = reading_service.get_passage_content(row.content_key)
    question_rows = await reading_service.get_questions(db, passage_id)
    questions = [
        ReadingQuestion(
            id=q.id,
            passage_id=q.passage_id,
            question_order=q.question_order,
            **reading_service.get_question_content(q.content_key),
        )
        for q in question_rows
    ]

    passage = ReadingPassage.model_validate(row, from_attributes=True)
    return passage.model_copy(update={**content, "questions": questions})
