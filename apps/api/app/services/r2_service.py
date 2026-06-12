# WHAT: Talks to Cloudflare R2 (an S3-compatible object store) to generate
#       presigned upload URLs.
# WHY:  File bytes never pass through our API — the client uploads directly
#       to R2 using a short-lived presigned PUT URL. This keeps uploads off
#       our compute and bandwidth entirely. boto3's S3 client works against
#       R2 because R2 implements the S3 API; we just point it at R2's
#       account-specific endpoint instead of AWS.

import uuid

import boto3
from botocore.config import Config

from app.core.config import settings

# Matches packages/shared/src/constants/limits.ts MAX_FILE_SIZE_BYTES — keep
# the two in sync if this ever changes.
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

PRESIGNED_URL_EXPIRES_IN = 900  # 15 minutes, in seconds

_client = boto3.client(
    "s3",
    endpoint_url=settings.r2_endpoint,
    aws_access_key_id=settings.r2_access_key_id,
    aws_secret_access_key=settings.r2_secret_access_key,
    config=Config(signature_version="s3v4"),
    region_name="auto",
)


def build_object_key() -> str:
    """A fresh, unguessable object key under the uploads/ prefix."""
    return f"uploads/{uuid.uuid4()}"


def presigned_put(object_key: str, content_type: str, expires: int = PRESIGNED_URL_EXPIRES_IN) -> str:
    """A presigned URL the client can PUT the file bytes to directly."""
    return _client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.r2_bucket, "Key": object_key, "ContentType": content_type},
        ExpiresIn=expires,
    )
