"""The Phase 1 analysis pipeline: detect → measure → listen → merge.

Source separation (Phase 4) slots in between detection and measurement; until then a
detected full mix is analysed as-is and the caller is told so through
`VocalProfile.analysis_notes`.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis import detector, merger, qualitative, spectral
from app.models.schemas import SourceType, VocalProfile


def analyze_file(
    path: str | Path,
    genre: str | None = None,
    use_llm: bool = True,
) -> VocalProfile:
    """Run the full analysis on an audio file and return the merged profile."""
    audio_path = str(path)
    notes: list[str] = []

    y, sr = spectral.load_audio(audio_path)
    source = detector.detect_samples(y, sr)
    if source.source_type is SourceType.FULL_MIX:
        notes.append(
            "Detected a full mix rather than a dry vocal. Analysed as-is — vocal isolation "
            "arrives in Phase 4, so these measurements include the instrumental."
        )

    features = spectral.analyze_samples(y, sr)

    heard = None
    if use_llm:
        try:
            heard = qualitative.analyze(audio_path, genre=genre)
        except qualitative.QualitativeUnavailableError as exc:
            notes.append(f"Listening pass skipped: {exc}")
    else:
        notes.append("Listening pass disabled; spectral measurements only.")

    return merger.merge(features, heard, source, genre=genre, notes=notes)
