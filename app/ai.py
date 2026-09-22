"""AI assessment pipeline.

One well-prompted Gemini vision call per submission (no agent orchestration),
constrained to OneAquaHealth's published indicator list, with strict output
sanitization and a deterministic mock mode when no API key is configured.
"""
import json
import logging
import random
import time

from google import genai
from google.genai import types as genai_types

from .config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are assessing a citizen-submitted freshwater ecosystem observation \
for the OneAquaHealth project. Analyze the provided photo and text description \
specifically for these indicators:

- riparian_vegetation_degradation — loss of streamside plant cover
- artificial_light_at_night — lighting near the water body
- trash_or_debris — visible trash or debris in or around the water
- chemical_or_pharmaceutical_contamination — unusual water color, foam, sheen, \
or odor cues mentioned in the text

In the JSON output, "indicators_detected" MUST contain ONLY these exact strings \
(verbatim, lowercase, with underscores). Do not invent other indicator names.

Return ONLY valid JSON in this exact shape:
{
  "indicators_detected": ["..."],
  "confidence": 0.0,
  "reasoning": "plain-language explanation of what was observed and why \
it matters for stream/ecosystem health"
}

If none are present, return an empty indicators_detected array and explain why."""

VALID_INDICATORS = {
    "riparian_vegetation_degradation",
    "artificial_light_at_night",
    "trash_or_debris",
    "chemical_or_pharmaceutical_contamination",
}


class AIAssessmentError(Exception):
    """Raised when the AI call fails or returns unusable output."""


def _mock_assessment(text_description: str) -> dict:
    """Deterministic keyword fallback so the pipeline runs with no API key."""
    text = text_description.lower()
    indicators = []
    if any(w in text for w in ("trash", "litter", "bottle", "can ", "plastic", "debris")):
        indicators.append("trash_or_debris")
    if any(w in text for w in ("erosion", "bare", "no plants", "cleared", "dead vegetat", "bank")):
        indicators.append("riparian_vegetation_degradation")
    if any(w in text for w in ("light", "lamp", "streetlight", "glow", "lantern")):
        indicators.append("artificial_light_at_night")
    if any(w in text for w in ("foam", "smell", "odor", "colour", "color", "rainbow", "sheen")):
        indicators.append("chemical_or_pharmaceutical_contamination")

    reasoning = (
        "[Assessment preview] Based on the description "
        f"\"{text_description[:120]}\", indicator analysis flagged: "
        + (", ".join(indicators) if indicators else "no listed indicators")
        + ". Connect an AI provider key to enable full vision-model assessment."
    )
    confidence = round(random.uniform(0.55, 0.9) if indicators else 0.3, 2)
    return {"indicators_detected": indicators, "confidence": confidence, "reasoning": reasoning}


_TRANSIENT_MARKERS = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "Deadline", "timed out")
_MAX_ATTEMPTS = 3


def _gemini_assessment(data: bytes, mime: str, text_description: str) -> dict:
    """Single well-prompted call, with bounded retry on transient provider errors
    (free-tier 503 'high demand' / 429 rate limits) so a demo never dies to a blip."""
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=[
                    genai_types.Part.from_bytes(data=data, mime_type=mime),
                    f"Text description from citizen: {text_description!r}",
                ],
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            return json.loads(response.text)
        except json.JSONDecodeError:
            raise  # model answered with garbage — retrying will not help
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            if not any(marker in msg for marker in _TRANSIENT_MARKERS):
                raise
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(1.5 * (2**attempt))  # 1.5s, 3s
    raise last_exc  # pragma: no cover — loop always returns or raises


def assess(data: bytes, mime: str, text_description: str) -> dict:
    """Assess a submission. Returns indicators, confidence, reasoning.

    Raises AIAssessmentError on failure so the API can surface it clearly.
    """
    if not settings.GEMINI_API_KEY:
        return _mock_assessment(text_description)
    try:
        result = _gemini_assessment(data, mime, text_description)
    except json.JSONDecodeError as exc:
        raise AIAssessmentError(f"Model returned non-JSON output: {exc}") from exc
    except Exception as exc:
        raise AIAssessmentError(f"Gemini call failed: {exc}") from exc

    # Sanitize: the model may only report known indicators.
    raw = result.get("indicators_detected", [])
    indicators = [i for i in raw if i in VALID_INDICATORS]
    unknown = [i for i in raw if i not in VALID_INDICATORS]
    reasoning = (result.get("reasoning") or "").strip()
    if unknown:
        reasoning = (
            f"{reasoning} (Model also mentioned unlisted observation(s): "
            f"{', '.join(unknown)} — ignored.)"
        ).strip()
    if not reasoning:
        reasoning = "The model did not provide a reasoning trail."

    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    return {"indicators_detected": indicators, "confidence": confidence, "reasoning": reasoning}
