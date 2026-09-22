import logging
from datetime import datetime, timezone

import httpx

from .config import FHIR_BASE_URL

logger = logging.getLogger(__name__)

CODE_TEXT = "Freshwater ecosystem citizen assessment"
TIMEOUT = 20.0


class FHIRError(Exception):
    """Raised when the FHIR server returns an error or unreachable."""


def observation_to_fhir(
    *,
    ai_reasoning: str,
    ai_indicators: list[str],
    ai_confidence: float,
    created_at: datetime,
) -> dict:
    """Map a validated observation to an FHIR Observation resource (PRD section 10)."""
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {"text": CODE_TEXT},
        "valueString": ai_reasoning,
        "component": [
            {"code": {"text": "indicator"}, "valueString": indicator}
            for indicator in ai_indicators
        ],
        "note": [{"text": f"Confidence: {ai_confidence}"}],
        "effectiveDateTime": created_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def post_to_fhir(resource: dict) -> str:
    """POST the resource to the FHIR server and return the created resource id."""
    url = f"{FHIR_BASE_URL}/Observation"
    try:
        resp = httpx.post(url, json=resource, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise FHIRError(f"FHIR server unreachable at {url}: {exc}") from exc
    if resp.status_code not in (200, 201):
        raise FHIRError(f"FHIR server returned {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    fhir_id = body.get("id") or body.get("resource", {}).get("id")
    if not fhir_id:
        raise FHIRError(f"FHIR server response missing resource id: {resp.text[:500]}")
    return fhir_id
