from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.generated import PaginatedUserMnemonic, UserMnemonic as UserMnemonicSchema
from app.services import kanji_service

router = APIRouter()


@router.get("/me/mnemonics", response_model=PaginatedUserMnemonic)
async def list_my_mnemonics(
    user: User = Depends(get_current_user),
    page_params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
) -> PaginatedUserMnemonic:
    """Requires auth. Returns only the kanji this user has written a custom
    mnemonic for, ordered by most recently edited first."""
    rows, total = await kanji_service.list_user_mnemonics(db, user.id, page_params)
    return PaginatedUserMnemonic(
        data=[
            UserMnemonicSchema(
                character=row.kanji_character,
                user_mnemonic=row.mnemonic,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=total,
        page=page_params.page,
        page_size=page_params.page_size,
    )
