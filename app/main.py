"""Riparia — validation middleware for citizen freshwater observations.

API v1: versioned REST endpoints under /api/v1, session auth for reviewers,
rate limiting on public endpoints, security headers, consistent error
envelope, and OpenAPI docs at /docs.
"""
import json
import logging
import uuid

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlmodel import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from .ai import AIAssessmentError, assess
from .auth import (
    end_session,
    require_reviewer,
    require_reviewer_with_csrf,
    start_session,
    verify_credentials,
)
from .config import PHOTO_DIR, settings
from .db import get_session, init_db
from .fhir import FHIRError, observation_to_fhir, post_to_fhir
from .models import Observation, ObservationStatus
from .photo_sanitizer import PhotoValidationError, sanitize_photo
from .storage import delete_photo, photo_url, put_photo

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

limiter = Limiter(key_func=get_remote_address)
init_db()

app = FastAPI(
    title="Riparia API",
    description=(
        "Validation middleware for citizen-submitted freshwater observations. "
        "AI-assisted indicator assessment with mandatory human review, committed "
        "as HL7 FHIR Observations for municipal and public-health interoperability."
    ),
    version="1.0.0",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "rate_limited", "message": "Too many requests. Retry shortly."}},
        headers={"Retry-After": "60"},
    )


# --- Security headers -------------------------------------------------------
CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        h.setdefault("Content-Security-Policy", CSP)
        if settings.ENVIRONMENT == "production":
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
    max_age=600,
)
app.add_middleware(SlowAPIMiddleware)


# --- Helpers ----------------------------------------------------------------
def _err(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def observation_to_dict(obs: Observation) -> dict:
    return {
        "id": obs.id,
        "photo_url": photo_url(obs.photo_key),
        "text_description": obs.text_description,
        "ai_indicators": json.loads(obs.ai_indicators),
        "ai_confidence": obs.ai_confidence,
        "ai_reasoning": obs.ai_reasoning,
        "status": (
            obs.status.value if isinstance(obs.status, ObservationStatus) else str(obs.status)
        ),
        "fhir_id": obs.fhir_id,
        "reviewed_by": obs.reviewed_by,
        "created_at": obs.created_at.isoformat(),
    }


# --- Public endpoints -------------------------------------------------------
@app.get("/api/health")
async def health():
    """Liveness probe for Render health checks and uptime monitors."""
    return {"status": "ok", "service": "riparia", "version": "1.0.0"}


@app.post("/api/v1/observations", status_code=201)
@limiter.limit(settings.RATE_LIMIT_SUBMIT)
async def create_observation(
    request: Request,
    text_description: str = Form(..., min_length=3, max_length=2000),
    photo: UploadFile = File(...),
    session=Depends(get_session),
):
    """Citizen submits photo + text -> AI assessment -> saved as pending.

    Open endpoint by design (citizen-facing), protected by strict rate limiting
    and the upload sanitizer.
    """
    raw = await photo.read()
    try:
        data, mime = await run_in_threadpool(sanitize_photo, raw)

        key = f"photos/{uuid.uuid4().hex}" + (".png" if mime == "image/png" else ".jpg")
        await run_in_threadpool(put_photo, key, data, mime)
    except PhotoValidationError as exc:
        raise _err("invalid_photo", str(exc), 400) from exc
    except Exception as exc:
        raise _err("storage_error", f"Failed to store photo: {exc}", 502) from exc

    obs = Observation(photo_key=key, text_description=text_description.strip())
    try:
        result = await run_in_threadpool(assess, data, mime, obs.text_description)
    except AIAssessmentError as exc:
        await run_in_threadpool(delete_photo, key)
        raise _err("ai_error", f"AI assessment failed: {exc}", 502) from exc

    obs.ai_indicators = json.dumps(result["indicators_detected"])
    obs.ai_confidence = result["confidence"]
    obs.ai_reasoning = result["reasoning"]
    obs.status = ObservationStatus.pending

    session.add(obs)
    session.commit()
    session.refresh(obs)
    return observation_to_dict(obs)


@app.get("/api/v1/observations")
def list_observations(
    status: ObservationStatus | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session=Depends(get_session),
):
    """All observations, newest first. Filterable by status, paginated."""
    stmt = select(Observation).order_by(Observation.created_at.desc())
    if status:
        stmt = stmt.where(Observation.status == status)
    rows = session.exec(stmt.limit(limit).offset(offset)).all()
    total = session.exec(select(func.count()).select_from(Observation)).one()
    return {
        "items": [observation_to_dict(o) for o in rows],
        "pagination": {"limit": limit, "offset": offset},
        "total": total[0],
    }


# --- Reviewer endpoints (session-authenticated) -----------------------------
@app.post("/api/v1/auth/login")
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Reviewer login. Sets a signed, HttpOnly session cookie."""
    if not verify_credentials(username, password):
        raise _err("invalid_credentials", "Invalid username or password", 401)
    response = JSONResponse({"ok": True})
    csrf = start_session(response, username)
    response.set_cookie("riparia_csrf", csrf, max_age=12 * 3600, samesite="lax", path="/")
    return response


@app.post("/api/v1/auth/logout")
async def logout(request: Request):
    response = JSONResponse({"ok": True})
    end_session(response)
    return response


@app.get("/api/v1/queue")
def get_queue(
    reviewer: str = Depends(require_reviewer),
    session=Depends(get_session),
):
    """Pending observations for the reviewer dashboard (auth required)."""
    stmt = (
        select(Observation)
        .where(Observation.status == ObservationStatus.pending)
        .order_by(Observation.created_at.asc())  # oldest first: fair review order
    )
    rows = session.exec(stmt).all()
    return {"items": [observation_to_dict(o) for o in rows]}


@app.post("/api/v1/observations/{observation_id}/approve")
async def approve_observation(
    observation_id: int,
    request: Request,
    x_csrf_token: str | None = Header(None),
    session=Depends(get_session),
):
    """Approve: maps to FHIR, POSTs to the FHIR server, marks approved."""
    reviewer = require_reviewer_with_csrf(request, x_csrf_token or "")
    obs = session.get(Observation, observation_id)
    if obs is None:
        raise _err("not_found", "Observation not found", 404)
    if obs.status != ObservationStatus.pending:
        raise _err("invalid_status", f"Observation is {obs.status.value}, not pending", 409)

    resource = observation_to_fhir(
        ai_reasoning=obs.ai_reasoning,
        ai_indicators=json.loads(obs.ai_indicators),
        ai_confidence=obs.ai_confidence,
        created_at=obs.created_at,
    )
    try:
        fhir_id = await run_in_threadpool(post_to_fhir, resource)
    except FHIRError as exc:
        raise _err("fhir_error", f"FHIR commit failed: {exc}", 502) from exc

    obs.status = ObservationStatus.approved
    obs.fhir_id = fhir_id
    obs.reviewed_by = reviewer
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return observation_to_dict(obs)


@app.post("/api/v1/observations/{observation_id}/reject")
async def reject_observation(
    observation_id: int,
    request: Request,
    x_csrf_token: str | None = Header(None),
    session=Depends(get_session),
):
    """Reject: marks rejected; nothing is sent to the FHIR server."""
    reviewer = require_reviewer_with_csrf(request, x_csrf_token or "")
    obs = session.get(Observation, observation_id)
    if obs is None:
        raise _err("not_found", "Observation not found", 404)
    if obs.status != ObservationStatus.pending:
        raise _err("invalid_status", f"Observation is {obs.status.value}, not pending", 409)
    obs.status = ObservationStatus.rejected
    obs.reviewed_by = reviewer
    session.add(obs)
    session.commit()
    session.refresh(obs)
    return observation_to_dict(obs)


# --- Static frontend ---------------------------------------------------------
app.mount("/photos", StaticFiles(directory=str(PHOTO_DIR)), name="photos")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
