# WHAT: Talks to Cloudflare R2 (an S3-compatible object store) to generate
#       presigned upload URLs.
# WHY:  File bytes never pass through our API — the client uploads directly
#       to R2 using a short-lived presigned PUT URL. This keeps uploads off
#       our compute and bandwidth entirely. boto3's S3 client works against
#       R2 because R2 implements the S3 API; we just point it at R2's
#       account-specific endpoint instead of AWS.

import json
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


def put_json(object_key: str, data: dict) -> None:
    """Write a JSON blob straight to R2 — used for reading-comprehension
    passage/question content, which the API server writes server-side
    (unlike file uploads, which go client -> R2 directly via presigned_put)."""
    _client.put_object(
        Bucket=settings.r2_bucket,
        Key=object_key,
        # ensure_ascii=False: without it, Japanese text gets escaped to
        # \uXXXX sequences, which bloats the JSON and is harder to debug.
        Body=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def get_json(object_key: str) -> dict:
    response = _client.get_object(Bucket=settings.r2_bucket, Key=object_key)
    return json.loads(response["Body"].read().decode("utf-8"))
