import json
import random
from pathlib import Path

from google import genai
from google.genai import types as genai_types

from .config import GEMINI_API_KEY, GEMINI_MODEL, MOCK_AI

SYSTEM_PROMPT = """You are assessing a citizen-submitted freshwater ecosystem observation \
for the OneAquaHealth project. Analyze the provided photo and text description \
specifically for these indicators:

- Riparian vegetation degradation (loss of streamside plant cover)
- Artificial light at night near the water body
- Visible trash or debris
- Signs consistent with chemical or pharmaceutical contamination \
(unusual water color, foam, odor cues mentioned in the text)

Return ONLY valid JSON in this exact shape:
{
  "indicators_detected": ["..."],
  "confidence": 0.0,
  "reasoning": "plain-language explanation of what was observed and why \
it matters for stream/ecosystem health"
}

Do not invent indicators outside this list. If none are present,
return an empty indicators_detected array and explain why."""

VALID_INDICATORS = {
    "riparian_vegetation_degradation",
    "artificial_light_at_night",
    "trash_or_debris",
    "chemical_or_pharmaceutical_contamination",
}

class AIAssessmentError(Exception):
    """Raised when the AI call fails or returns unusable output."""


def _mock_assessment(text_description: str) -> dict:
    """Deterministic-ish fake AI output so the full pipeline runs with no API key."""
    text = text_description.lower()
    indicators = []
    if any(w in text for w in ("trash", "litter", "bottle", "can", "plastic", "debris")):
        indicators.append("trash_or_debris")
    if any(w in text for w in ("erosion", "bare", "no plants", "cleared", "dead vegetat", "bank")):
        indicators.append("riparian_vegetation_degradation")
    if any(w in text for w in ("light", "lamp", "streetlight", "glow", "lantern")):
        indicators.append("artificial_light_at_night")
    if any(w in text for w in ("foam", "smell", "odor", "colour", "color", "rainbow", "sheen")):
        indicators.append("chemical_or_pharmaceutical_contamination")

    reasoning = (
        f"[MOCK AI — no GEMINI_API_KEY set] Based on the description "
        f"\"{text_description[:120]}\", keyword matching flagged: "
        + (", ".join(indicators) if indicators else "no listed indicators")
        + ". A real model call will replace this once an API key is configured."
    )
    confidence = round(random.uniform(0.55, 0.9) if indicators else 0.3, 2)
    return {"indicators_detected": indicators, "confidence": confidence, "reasoning": reasoning}


def _gemini_assessment(photo_path: Path, text_description: str) -> dict:
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            genai_types.Part.from_bytes(data=photo_path.read_bytes(), mime_type=photo_to_mime(photo_path)),
            f"Text description from citizen: {text_description!r}",
        ],
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return json.loads(response.text)


def photo_to_mime(photo_path: Path) -> str:
    suffix = photo_path.suffix.lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(suffix, "image/jpeg")


def assess(photo_path: Path, text_description: str) -> dict:
    """Assess a citizen submission, returning (indicators, confidence, reasoning).

    Raises AIAssessmentError on failure so the API can surface it clearly.
    """
    if MOCK_AI:
        return _mock_assessment(text_description)
    try:
        result = _gemini_assessment(photo_path, text_description)
    except json.JSONDecodeError as exc:
        raise AIAssessmentError(f"Model returned non-JSON output: {exc}") from exc
    except Exception as exc:
        raise AIAssessmentError(f"Gemini call failed: {exc}") from exc

    # Sanitize: the model must only ever report known indicators.
    raw = result.get("indicators_detected", [])
    indicators = [i for i in raw if i in VALID_INDICATORS]
    unknown = [i for i in raw if i not in VALID_INDICATORS]
    if unknown:
        result["reasoning"] = (
            f"{result.get('reasoning', '')} (Model also mentioned unlisted "
            f"observation(s): {', '.join(unknown)} — ignored.)"
        ).strip()
    try:
        confidence = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = (result.get("reasoning") or "").strip() or "The model did not provide a reasoning trail."

    return {
        "indicators_detected": indicators,
        "confidence": confidence,
        "reasoning": reasoning,
    }
