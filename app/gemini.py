"""Gemini adapter. Uses Vertex AI on Cloud Run (no key) or an API key locally.

Only abstract scores and menu candidates are sent. No image or identity ever reaches the model.
"""
import json
import logging
import os

from .config import GEMINI_MODEL

log = logging.getLogger("moodbrew.gemini")

_PROMPT = (
    "You are the playful barista-concierge of a premium cafe. The guest just played a "
    "face-expression game and their vibe is '{vibe}' (scores 0-1: {scores}). "
    "Choose exactly one drink and one snack from the candidates, and write ONE warm, witty "
    "line (max 22 words, no emojis, never mention their face, never say they look sad). "
    "Reply as JSON: {{\"drink_id\":\"..\",\"snack_id\":\"..\",\"line\":\"..\"}}.\n"
    "Drinks: {drinks}\nSnacks: {snacks}"
)


def _build_client():
    """Create a google-genai client, or return None when nothing is configured."""
    try:
        from google import genai  # pylint: disable=import-outside-toplevel
    except ImportError:
        return None
    if os.getenv("GEMINI_API_KEY"):
        return genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if project:
        return genai.Client(
            vertexai=True, project=project, location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        )
    return None


class GeminiPicker:
    """Asks Gemini to choose among candidates. Returns None on any failure."""

    def __init__(self) -> None:
        self._client = None
        self._tried = False

    @property
    def enabled(self) -> bool:
        """True when a Gemini client could be built."""
        if not self._tried:
            self._tried = True
            self._client = _build_client()
        return self._client is not None

    def pick(self, vibe: str, scores: dict, drinks: list[dict], snacks: list[dict]) -> dict | None:
        """Return {'drink_id','snack_id','line'} or None."""
        if not self.enabled:
            return None
        from google.genai import types  # pylint: disable=import-outside-toplevel

        prompt = _PROMPT.format(
            vibe=vibe,
            scores=", ".join(f"{k}={v:.2f}" for k, v in scores.items()),
            drinks=json.dumps(drinks),
            snacks=json.dumps(snacks),
        )
        try:
            reply = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.8, max_output_tokens=300
                ),
            )
            data = json.loads(reply.text)
            return data if isinstance(data, dict) else None
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("gemini unavailable, using deterministic pick: %s", type(exc).__name__)
            return None
