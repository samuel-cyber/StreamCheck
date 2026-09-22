import json
import uuid
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlmodel import Session, select

from .ai import AIAssessmentError, assess
from .config import ALLOWED_PHOTO_TYPES, MAX_PHOTO_BYTES, PHOTO_DIR, PUBLIC_BASE_URL
from .fhir import FHIRError, observation_to_fhir, post_to_fhir
from .models import Observation, engine, init_db

init_db()

app = FastAPI(title="StreamCheck", description="AI-supported freshwater observation validation layer (OneAquaHealth Track 3)")


def observation_to_dict(obs: Observation) -> dict:
    return {
        "id": obs.id,
        "photo_path": obs.photo_path,
        "photo_url": f"{PUBLIC_BASE_URL}/photos/{obs.photo_path}",
        "text_description": obs.text_description,
        "ai_indicators": json.loads(obs.ai_indicators),
        "ai_confidence": obs.ai_confidence,
        "ai_reasoning": obs.ai_reasoning,
        "status": obs.status,
        "fhir_id": obs.fhir_id,
        "created_at": obs.created_at.isoformat(),
    }


def _validate_photo(photo: UploadFile) -> bytes:
    if photo.content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported photo type {photo.content_type}. Allowed: {sorted(ALLOWED_PHOTO_TYPES)}")
    data = photo.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo exceeds 10 MB limit")
    try:
        photo.file.seek(0)
        Image.open(photo.file).verify()  # reject corrupt files the AI call would choke on
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Photo file is not a valid image: {exc}") from exc
    finally:
        photo.file.seek(0)
    return data


@app.post("/observations")
async def create_observation(
    text_description: str = Form(..., min_length=3, max_length=2000),
    photo: UploadFile = File(...),
):
    """Citizen submits photo + text -> AI assessment -> saved as pending (PRD section 8)."""
    data = _validate_photo(photo)

    ext = (photo.filename or "photo.jpg").rsplit(".", 1)[-1].lower() or "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    photo_path = PHOTO_DIR / filename
    photo_path.write_bytes(data)

    obs = Observation(photo_path=filename, text_description=text_description.strip())
    try:
        result = await run_in_threadpool(assess, photo_path, obs.text_description)
    except AIAssessmentError as exc:
        photo_path.unlink(missing_ok=True)
        # PRD: surface errors clearly in the API response rather than failing silently.
        raise HTTPException(status_code=502, detail=f"AI assessment failed: {exc}") from exc

    obs.ai_indicators = json.dumps(result["indicators_detected"])
    obs.ai_confidence = result["confidence"]
    obs.ai_reasoning = result["reasoning"]
    obs.status = "pending"

    with Session(engine) as session:
        session.add(obs)
        session.commit()
        session.refresh(obs)
        return JSONResponse(status_code=201, content=observation_to_dict(obs))


@app.get("/queue")
def get_queue():
    """All pending observations for the reviewer dashboard."""
    with Session(engine) as session:
        rows = session.exec(select(Observation).where(Observation.status == "pending")).all()
        return [observation_to_dict(row) for row in rows]


@app.get("/observations")
def list_observations(status: Optional[str] = None):
    """All observations, optionally filtered by status (for results view)."""
    statement = select(Observation)
    if status:
        if status not in ("pending", "approved", "rejected"):
            raise HTTPException(status_code=400, detail="status must be pending, approved, or rejected")
        statement = statement.where(Observation.status == status)
    with Session(engine) as session:
        rows = session.exec(statement).all()
        return [observation_to_dict(row) for row in rows]


@app.post("/observations/{observation_id}/approve")
async def approve_observation(observation_id: int):
    """Human approval: map to FHIR, POST to HAPI server, mark approved."""
    with Session(engine) as session:
        obs = session.get(Observation, observation_id)
        if obs is None:
            raise HTTPException(status_code=404, detail="Observation not found")
        if obs.status != "pending":
            raise HTTPException(status_code=409, detail=f"Observation is {obs.status}, not pending")

        resource = observation_to_fhir(
            ai_reasoning=obs.ai_reasoning,
            ai_indicators=json.loads(obs.ai_indicators),
            ai_confidence=obs.ai_confidence,
            created_at=obs.created_at,
        )
        try:
            fhir_id = await run_in_threadpool(post_to_fhir, resource)
        except FHIRError as exc:
            raise HTTPException(status_code=502, detail=f"FHIR commit failed: {exc}") from exc

        obs.status = "approved"
        obs.fhir_id = fhir_id
        session.add(obs)
        session.commit()
        session.refresh(obs)
        return observation_to_dict(obs)


@app.post("/observations/{observation_id}/reject")
def reject_observation(observation_id: int):
    """Human rejection: mark rejected; nothing sent to FHIR."""
    with Session(engine) as session:
        obs = session.get(Observation, observation_id)
        if obs is None:
            raise HTTPException(status_code=404, detail="Observation not found")
        if obs.status != "pending":
            raise HTTPException(status_code=409, detail=f"Observation is {obs.status}, not pending")
        obs.status = "rejected"
        session.add(obs)
        session.commit()
        session.refresh(obs)
        return observation_to_dict(obs)


app.mount("/photos", StaticFiles(directory=PHOTO_DIR), name="photos")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
