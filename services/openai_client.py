"""OpenAI-backed calorie estimation for freeform food descriptions."""

from __future__ import annotations

import json
import os

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You are a nutrition estimation assistant. Given a freeform list of foods "
    "and drinks a person consumed, estimate the total calories. "
    "Respond with strict JSON only, in the form {\"total_calories\": <number>}."
)


class CalorieEstimationError(Exception):
    """Raised when a calorie estimate could not be obtained from OpenAI."""


def estimate_calories(food_text: str) -> float:
    """Return an estimated total calorie count for ``food_text``.

    Raises ``CalorieEstimationError`` on any failure (missing API key, network
    error, malformed response). Callers are responsible for reporting the
    traceback and deciding how to handle the failure.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise CalorieEstimationError("OPENAI_API_KEY environment variable is not set.")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise CalorieEstimationError("The 'openai' package is not installed.") from exc

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": food_text},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)
        return float(parsed["total_calories"])
    except CalorieEstimationError:
        raise
    except Exception as exc:
        raise CalorieEstimationError(f"OpenAI calorie estimation failed: {exc}") from exc
