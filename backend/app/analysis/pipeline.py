"""The analysis pipeline: detect → separate if needed → measure → listen → merge.

Separation only runs when the detector says the upload is a full mix, because it is
slow and because running it on a dry vocal degrades a clean signal for nothing.
Whatever happens, the profile says which it was: analysis notes are how the result
explains what it actually measured.
"""

from __future__ import annotations

from pathlib import Path

from app.analysis import detector, merger, qualitative, spectral
from app.models.schemas import SourceType, VocalProfile
from app.separation import demucs_runner


def analyze_file(
    path: str | Path,
    genre: str | None = None,
    use_llm: bool = True,
    separate: bool = True,
) -> VocalProfile:
    """Run the full analysis on an audio file and return the merged profile."""
    audio_path = str(path)
    notes: list[str] = []

    y, sr = spectral.load_audio(audio_path)
    source = detector.detect_samples(y, sr)

    analysed_path = audio_path
    extracted_vocal = False
    separated = None

    try:
        if source.source_type is SourceType.FULL_MIX:
            separated, note = _isolate(audio_path, separate)
            notes.append(note)
            if separated is not None:
                analysed_path = str(separated.vocal_path)
                y, sr = spectral.load_audio(analysed_path)
                extracted_vocal = True

        features = spectral.analyze_samples(y, sr)

        heard = None
        if use_llm:
            try:
                heard = qualitative.analyze(
                    analysed_path, genre=genre, extracted_vocal=extracted_vocal
                )
            except qualitative.QualitativeUnavailableError as exc:
                notes.append(f"Listening pass skipped: {exc}")
        else:
            notes.append("Listening pass disabled; spectral measurements only.")
    finally:
        if separated is not None:
            demucs_runner.cleanup(separated)

    return merger.merge(features, heard, source, genre=genre, notes=notes)


def _isolate(
    audio_path: str, separate: bool
) -> tuple[demucs_runner.Separated | None, str]:
    """Pull the vocal out of a mix, or explain why the mix was analysed as it is."""
    if not separate:
        return None, (
            "Detected a full mix and separation was turned off, so these measurements "
            "include the instrumental."
        )
    if not demucs_runner.available():
        return None, (
            "Detected a full mix but source separation is not installed, so these "
            "measurements include the instrumental."
        )

    try:
        result = demucs_runner.separate_vocal(audio_path)
    except demucs_runner.SeparationError as exc:
        return None, (
            f"Detected a full mix but separation failed ({exc}), so these measurements "
            "include the instrumental."
        )

    return result, (
        f"Detected a full mix, so the vocal was isolated with {result.model} "
        f"({result.seconds:.0f}s) and everything below describes that stem. Expect minor "
        "separation artifacts."
    )
