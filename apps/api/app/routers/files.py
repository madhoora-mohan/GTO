# WHAT: The `/files/*` HTTP routes — presigned R2 uploads.
# WHY:  Keeps the upload flow's HTTP shape (auth, status codes, schemas)
#       separate from the R2/DB logic in services/file_service.py.

from fastapi import APIRouter, Depends, status
from pydantic import AnyUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.generated import FileConfirmInput, FileMetadata, FilePresignInput, FilePresignResponse
from app.services import file_service

router = APIRouter()


@router.post("/presign", response_model=FilePresignResponse)
async def presign(
    body: FilePresignInput,
    _user: User = Depends(get_current_user),
) -> FilePresignResponse:
    """Generate a presigned R2 PUT URL for an upload."""
    object_key, upload_url, expires_in = file_service.create_presigned_upload(
        body.filename, body.mime_type, body.size_bytes
    )
    return FilePresignResponse(
        object_key=object_key, upload_url=AnyUrl(upload_url), expires_in=expires_in
    )


@router.post("/confirm", response_model=FileMetadata, status_code=status.HTTP_201_CREATED)
async def confirm(
    body: FileConfirmInput,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileMetadata:
    """Record the `files` metadata row for an object already uploaded to R2."""
    file_row = await file_service.confirm_upload(
        db, user.id, body.object_key, body.filename, body.mime_type, body.size_bytes
    )
    return FileMetadata.model_validate(file_row, from_attributes=True)
