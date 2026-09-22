#!/usr/bin/env py
"""FHIR mapping test with a hand-written static payload.

Per the PRD build-order note: validate the FHIR layer in isolation, before
wiring live AI output. Run with the API venv:

    py scripts/test_fhir_mapping.py
"""
import json
import sys
from datetime import UTC, datetime

import httpx

sys.path.insert(0, ".")

from app.config import settings
from app.fhir import observation_to_fhir

STATIC_PAYLOAD = {
    "ai_reasoning": "Static test payload: visible foam and discoloration on the "
    "water surface suggest possible contamination; sparse bank vegetation noted.",
    "ai_indicators": [
        "chemical_or_pharmaceutical_contamination",
        "riparian_vegetation_degradation",
    ],
    "ai_confidence": 0.82,
}


def main() -> int:
    resource = observation_to_fhir(
        created_at=datetime.now(UTC), **STATIC_PAYLOAD
    )
    print("Mapped FHIR Observation:")
    print(json.dumps(resource, indent=2))

    url = f"{settings.FHIR_BASE_URL}/Observation"
    print(f"\nPOST {url}")
    try:
        resp = httpx.post(url, json=resource, timeout=30)
    except httpx.HTTPError as exc:
        print(f"FAIL — unreachable: {exc}")
        return 1
    print(f"HTTP {resp.status_code}")
    if resp.status_code in (200, 201):
        fhir_id = resp.json().get("id")
        print(f"Created FHIR Observation/{fhir_id}")
        print(f"Verify: {settings.FHIR_BASE_URL}/Observation/{fhir_id}")
        return 0
    print(resp.text[:800])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
