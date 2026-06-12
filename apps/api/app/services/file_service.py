# WHAT: The DB-touching half of the R2 upload flow — validates presign
#       requests and writes the `files` metadata row on confirm.
# WHY:  routers/files.py stays thin; r2_service.py stays pure (no DB, no
#       HTTPException) so it's easy to reuse from anywhere that needs a
#       presigned URL.

import uuid

from fastapi import HTTPException, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.services.r2_service import MAX_FILE_SIZE_BYTES, build_object_key, presigned_put


def create_presigned_upload(filename: str, mime_type: str, size_bytes: int) -> tuple[str, str, int]:
    """Validate a presign request and return (object_key, upload_url, expires_in)."""
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"size_bytes exceeds the {MAX_FILE_SIZE_BYTES} byte limit",
        )

    object_key = build_object_key()
    upload_url = presigned_put(object_key, mime_type)
    return object_key, upload_url, 900


async def confirm_upload(
    db: AsyncSession,
    uploaded_by: uuid.UUID,
    object_key: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
) -> File:
    """Record the `files` metadata row for an object the client has already
    PUT to R2. Idempotent: re-confirming the same object_key updates the row
    rather than erroring, so a retried confirm call is safe."""
    stmt = (
        pg_insert(File)
        .values(
            object_key=object_key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            uploaded_by=uploaded_by,
        )
        .on_conflict_do_update(
            index_elements=[File.object_key],
            set_={
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size_bytes,
                "uploaded_by": uploaded_by,
            },
        )
        .returning(File)
    )
    result = await db.execute(stmt)
    file_row = result.scalar_one()
    await db.commit()
    return file_row
