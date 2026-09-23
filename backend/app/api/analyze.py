"""POST /analyze — upload a recording, get the profile and the three chains back.

Analysis is synchronous: pitch tracking dominates and a one-minute take takes a few
seconds, which is tolerable for V1. The stage-by-stage progress the UI shows is driven
by the client, not by the server streaming stages.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from app.analysis import spectral
from app.analysis.pipeline import analyze_file
from app.api.envelope import ApiError, ok
from app.db.repository import CatalogUnavailableError, PluginCatalog
from app.models.schemas import AnalysisResult, Tier
from app.recommendation.chain_builder import build_chains

router = APIRouter()

#: Formats librosa can open reliably.
ALLOWED_SUFFIXES = {".wav", ".flac", ".mp3", ".aiff", ".aif", ".ogg", ".m4a"}

#: Uploads above this are rejected before anything is read into memory.
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
_CHUNK = 1024 * 1024


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    genre: str | None = Form(default=None),
    use_llm: bool = Form(default=True),
) -> dict:
    """Analyse an uploaded recording and build a chain for each tier."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ApiError(
            f"{suffix or 'that file type'} is not supported — "
            f"upload {', '.join(sorted(ALLOWED_SUFFIXES))}",
            status_code=415,
        )

    with tempfile.NamedTemporaryFile(suffix=suffix) as scratch:
        await _save(file, Path(scratch.name))

        try:
            profile = analyze_file(scratch.name, genre=genre, use_llm=use_llm)
        except spectral.AudioTooShortError as exc:
            raise ApiError(str(exc), status_code=422) from exc
        except Exception as exc:  # librosa raises a wide range on malformed audio
            raise ApiError(f"could not read that audio: {exc}", status_code=422) from exc

    try:
        catalog = PluginCatalog.load()
        chains = build_chains(profile, catalog)
    except CatalogUnavailableError as exc:
        # The analysis is still worth returning; the chains are what is missing.
        profile.analysis_notes.append(f"Chains unavailable: {exc}")
        chains = []

    return ok(AnalysisResult(profile=profile, chains=chains))


async def _save(file: UploadFile, target: Path) -> None:
    """Stream the upload to disk, refusing anything oversized as it arrives."""
    written = 0
    with target.open("wb") as sink:
        while chunk := await file.read(_CHUNK):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                raise ApiError(
                    f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                    status_code=413,
                )
            sink.write(chunk)

    if written == 0:
        raise ApiError("the uploaded file is empty", status_code=422)


@router.get("/tiers")
def tiers() -> dict:
    """The tiers the UI can offer, so the labels live in one place."""
    return ok({"tiers": [tier.value for tier in Tier]})
