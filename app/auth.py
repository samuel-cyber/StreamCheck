"""Reviewer authentication.

Simple, auditable session auth: one reviewer account (credentials via env
vars), bcrypt-verified password, signed session cookie (itsdangerous), and
per-form CSRF tokens. The reviewer dashboard and all state-changing endpoints
require a valid session; citizen submission stays open by design with strict
rate limiting.
"""
import functools
import hmac
import secrets

import bcrypt
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, TimestampSigner

from .config import settings

_SESSION_COOKIE = "riparia_session"
_MAX_AGE = 12 * 3600
_CSRF_SESSION_KEY = "csrf_token"


def _signer() -> TimestampSigner:
    return TimestampSigner(settings.SESSION_SECRET)


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time-ish credential check against configured reviewer account."""
    user_ok = hmac.compare_digest(username, settings.REVIEWER_USERNAME)
    try:
        pass_ok = bcrypt.checkpw(password.encode(), settings.REVIEWER_PASSWORD_HASH.encode())
    except ValueError:
        pass_ok = False
    return user_ok and pass_ok


def start_session(response, username: str) -> str:
    """Create a signed session cookie + CSRF token. Returns the CSRF token."""
    token = secrets.token_urlsafe(32)
    signed = _signer().sign(f"{username}:{token}").decode()
    response.set_cookie(
        _SESSION_COOKIE, signed, max_age=_MAX_AGE, httponly=True,
        secure=settings.ENVIRONMENT == "production", samesite="lax", path="/",
    )
    # CSRF token rides inside the signed cookie value, so it is tamper-proof.
    return token


def csrf_token_for(request: Request) -> str:
    """Extract the CSRF token embedded in the session cookie."""
    raw = request.cookies.get(_SESSION_COOKIE)
    if not raw:
        return ""
    try:
        payload = _signer().unsign(raw, max_age=_MAX_AGE).decode()
        return payload.split(":", 1)[1]
    except BadSignature:
        return ""


def end_session(response) -> None:
    response.delete_cookie(_SESSION_COOKIE, path="/")


def current_reviewer(request: Request) -> str | None:
    raw = request.cookies.get(_SESSION_COOKIE)
    if not raw:
        return None
    try:
        payload = _signer().unsign(raw, max_age=_MAX_AGE).decode()
        return payload.split(":", 1)[0]
    except BadSignature:
        return None


def require_reviewer(request: Request) -> str:
    reviewer = current_reviewer(request)
    if not reviewer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Session"},
        )
    return reviewer


def require_reviewer_with_csrf(request: Request, csrf_token: str) -> str:
    reviewer = require_reviewer(request)
    expected = csrf_token_for(request)
    if not expected or not csrf_token or not hmac.compare_digest(csrf_token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return reviewer


def reviewer_required(fn):
    """Dependency for sync/async routes: 401 unless a valid session exists."""
    @functools.wraps(fn)
    async def wrapper(*args, request: Request = None, **kwargs):
        if request is None:
            raise HTTPException(status_code=500, detail="Auth misconfigured")
        require_reviewer(request)
        return await fn(*args, request=request, **kwargs)
    return wrapper
