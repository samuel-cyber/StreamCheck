"""Photo storage abstraction.

Production: Cloudflare R2 (S3 API) — chosen over Supabase Storage because R2
has zero egress fees, S3-compatible signed URLs without an extra service, and
keeps photos out of the database tier entirely. Buckets stay private; images
are served through short-lived signed URLs minted per request.
Local dev: plain files under data/photos/, so the stack runs with zero cloud
accounts configured.
"""
import logging

import boto3
from botocore.client import Config as BotoConfig

from .config import PHOTO_DIR, settings

logger = logging.getLogger(__name__)

_SIGN_TTL = 3600  # seconds a signed photo URL stays valid


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def storage_enabled() -> bool:
    return bool(
        settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY
    )


def put_photo(key: str, data: bytes, content_type: str) -> None:
    """Store photo bytes under a private key. Raises on storage failure."""
    if storage_enabled():
        _s3_client().put_object(
            Bucket=settings.R2_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
    else:
        # Local dev fallback: data/ is gitignored and ephemeral-safe.
        path = PHOTO_DIR / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def photo_url(key: str) -> str:
    """Signed read URL (prod) or static URL (local dev) for a stored photo."""
    if storage_enabled():
        url = _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.R2_BUCKET, "Key": key},
            ExpiresIn=_SIGN_TTL,
        )
        # Optional custom domain in front of the bucket (R2 public dev URL).
        if settings.R2_PUBLIC_BASE:
            url = f"{settings.R2_PUBLIC_BASE}/{key}"
        return url
    return f"{settings.PUBLIC_BASE_URL}/photos/{key}"


def delete_photo(key: str) -> None:
    if storage_enabled():
        _s3_client().delete_object(Bucket=settings.R2_BUCKET, Key=key)
    else:
        (PHOTO_DIR / key).unlink(missing_ok=True)
