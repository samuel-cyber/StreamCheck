"""Photo upload hardening pipeline.

1. Size limit enforced server-side before any parsing.
2. Content sniffing — magic bytes, not the client-declared MIME type.
3. Full decode to catch malformed/polyglot payloads.
4. EXIF GPS + metadata strip (citizen privacy — phone photos embed location).
5. Re-encode through Pillow so the stored file is a clean, normalized image.
"""
import io
import logging

from PIL import Image, features

from .config import settings

logger = logging.getLogger(__name__)

MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # RIFF....WEBP — checked below
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
}

# Absolute pixel ceiling — decompression-bomb guard (Pillow has its own cap,
# but we fail earlier and with a clearer error).
MAX_PIXELS = 40_000_000  # ~40 MP


class PhotoValidationError(Exception):
    pass


def sniff_type(head: bytes) -> str | None:
    for magic, mime in MAGIC.items():
        if head.startswith(magic):
            if mime == "image/webp":  # confirm WEBP fourcc inside RIFF container
                return "image/webp" if head[8:12] == b"WEBP" else None
            return mime
    return None


def sanitize_photo(raw: bytes) -> tuple[bytes, str]:
    """Validate + clean an upload. Returns (re-encoded bytes, normalized mime)."""
    if len(raw) > settings.MAX_PHOTO_BYTES:
        raise PhotoValidationError("Photo exceeds the 10 MB limit")
    if len(raw) < 64:
        raise PhotoValidationError("File too small to be a valid photo")

    declared = sniff_type(raw[:16])
    if declared not in settings.ALLOWED_PHOTO_TYPES:
        raise PhotoValidationError("Unsupported image format — upload JPEG, PNG, WebP, or GIF")

    try:
        Image.open(io.BytesIO(raw))
    except Exception as exc:
        raise PhotoValidationError(f"Corrupt or malformed image: {exc}") from exc

    return reencode(raw)


def reencode(raw: bytes) -> tuple[bytes, str]:
    """Decode fully, strip metadata, re-encode. Raises PhotoValidationError on bombs."""
    if not features.check("zlib"):  # pragma: no cover — Pillow always has zlib
        raise PhotoValidationError("Server image codec unavailable")
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            if im.width * im.height > MAX_PIXELS:
                raise PhotoValidationError("Image resolution too large")
            fmt = "PNG" if im.mode in ("RGBA", "LA", "P") else "JPEG"
            if fmt == "JPEG" and im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            # Saving without exif/icc params strips all metadata (incl. GPS).
            im.save(buf, format=fmt, quality=85, optimize=True)
            mime = "image/png" if fmt == "PNG" else "image/jpeg"
            return buf.getvalue(), mime
    except PhotoValidationError:
        raise
    except Exception as exc:
        raise PhotoValidationError(f"Image processing failed: {exc}") from exc
