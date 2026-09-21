"""Qualitative listening pass: Gemini 2.5 Pro hears the audio and describes it.

The spectral pass knows the numbers but not what they sound like; this pass knows
what it sounds like but cannot measure. `merger.py` reconciles the two.
"""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

from pydantic import ValidationError

from app.models.schemas import QualitativeAnalysis

MODEL = "gemini-2.5-pro"

#: Above this, upload via the Files API instead of inlining the bytes.
INLINE_LIMIT_BYTES = 18 * 1024 * 1024

PROMPT = """You are a senior mixing engineer listening to a vocal recording in order
to brief another engineer who cannot hear it.

Assess the recording and report:
- tonal_balance: where the vocal sits tonally — muddy, boxy, thin, harsh, dull, balanced —
  and roughly which frequencies are responsible.
- room_sound: is this a treated space, a bedroom, a reflective room? Is there audible
  reverb, slap, or boxiness from the room itself?
- dynamics: how even is the performance? Do words disappear or jump out? Is it already
  compressed?
- artifacts: clipping, distortion, plosives, mouth noise, clicks, background noise,
  bleed, or separation artifacts.
- genre_context: how the recording reads against the stated genre's conventions.
- issues: the concrete problems worth fixing, each with the processing category that
  addresses it and how badly it needs attention.

Judge only what you can actually hear. Do not invent problems to fill the list; a clean
recording should return few or no issues. Be specific and concrete — "boxy around 400 Hz,
like the mic was close to a wall" beats "sounds a bit off".

Category must be one of: EQ, COMPRESSION, DE_ESS, SATURATION, GATE, NOISE_REDUCTION,
PITCH_CORRECTION, REVERB, DELAY, LIMITER.
Severity must be one of: MINOR, MODERATE, CRITICAL.
"""


class QualitativeUnavailableError(RuntimeError):
    """Raised when the listening pass cannot run (no key, upload or API failure)."""


def analyze(
    path: str | Path,
    genre: str | None = None,
    extracted_vocal: bool = False,
    api_key: str | None = None,
) -> QualitativeAnalysis:
    """Send the audio to Gemini and return its structured assessment."""
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise QualitativeUnavailableError("GEMINI_API_KEY is not set")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise QualitativeUnavailableError(f"google-genai is not installed: {exc}") from exc

    audio_path = Path(path)
    client = genai.Client(api_key=key)

    try:
        audio_part = _audio_part(client, types, audio_path)
        response = client.models.generate_content(
            model=MODEL,
            contents=[audio_part, build_prompt(genre, extracted_vocal)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QualitativeAnalysis,
            ),
        )
    except QualitativeUnavailableError:
        raise
    except Exception as exc:  # the SDK raises a wide range of transport/API errors
        raise QualitativeUnavailableError(f"Gemini request failed: {exc}") from exc

    return parse_response(response.text)


def build_prompt(genre: str | None, extracted_vocal: bool) -> str:
    """Assemble the listening prompt, including the context the model needs."""
    parts = [PROMPT]
    if genre:
        parts.append(f"\nThe artist describes this as: {genre}. Judge it against that genre.")
    if extracted_vocal:
        parts.append(
            "\nThis vocal was extracted from a full mix by source separation. Expect minor "
            "separation artifacts (smearing, watery high end, faint bleed) and do not report "
            "them as problems with the recording itself unless they are severe."
        )
    return "".join(parts)


def parse_response(text: str | None) -> QualitativeAnalysis:
    """Validate the model's JSON reply into a `QualitativeAnalysis`."""
    if not text:
        raise QualitativeUnavailableError("Gemini returned an empty response")
    try:
        return QualitativeAnalysis.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise QualitativeUnavailableError(f"could not parse Gemini response: {exc}") from exc


def _audio_part(client, types, audio_path: Path):
    """Inline small files; upload large ones through the Files API."""
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "audio/wav"
    size = audio_path.stat().st_size
    if size <= INLINE_LIMIT_BYTES:
        return types.Part.from_bytes(data=audio_path.read_bytes(), mime_type=mime_type)
    return client.files.upload(file=str(audio_path))
