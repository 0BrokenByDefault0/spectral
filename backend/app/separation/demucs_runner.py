"""Demucs v4 vocal isolation, for uploads that turn out to be full mixes.

CPU is fine for V1 but not fast: roughly real time per minute of audio on a few cores,
which is why separation only runs when the detector says the upload is a mix.

The model is a few hundred megabytes and downloads on first use, so `available()` exists
to let callers degrade gracefully rather than hanging on a cold start.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: htdemucs is the v4 default: best quality per unit of time on CPU.
MODEL = "htdemucs"
#: Separation is slow; past this the caller is better off analysing the mix as-is.
TIMEOUT_SECONDS = 900


class SeparationError(RuntimeError):
    """Raised when separation could not run or produced nothing usable."""


@dataclass
class Separated:
    """Where the vocal stem landed, and what it cost to get it."""

    vocal_path: Path
    model: str
    seconds: float


def available() -> bool:
    """True when Demucs can be invoked at all."""
    try:
        import demucs  # noqa: F401
    except ImportError:
        return False
    return True


def separate_vocal(
    source: str | Path,
    destination: Path | None = None,
    model: str = MODEL,
    timeout: int = TIMEOUT_SECONDS,
) -> Separated:
    """Extract the vocal stem from a full mix.

    Runs Demucs as a subprocess rather than in-process: it is a long CPU-bound job that
    holds significant memory, and a subprocess can be timed out and reclaimed cleanly.
    """
    if not available():
        raise SeparationError("demucs is not installed")

    audio = Path(source)
    if not audio.exists():
        raise SeparationError(f"no such file: {audio}")

    holding = destination or Path(tempfile.mkdtemp(prefix="voxchain-separated-"))
    holding.mkdir(parents=True, exist_ok=True)

    command = [
        # The interpreter running us, not whatever "python" resolves to on PATH:
        # demucs lives in this environment, which a system python cannot see.
        sys.executable,
        "-m",
        "demucs.separate",
        "--two-stems",
        "vocals",  # we only need the voice; skip drums/bass/other
        "-n",
        model,
        "-o",
        str(holding),
        str(audio),
    ]

    from time import monotonic

    started = monotonic()
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise SeparationError(f"separation took longer than {timeout}s") from exc

    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        raise SeparationError(f"demucs failed: {tail[-1] if tail else 'no output'}")

    vocals = next(holding.rglob("vocals.*"), None)
    if vocals is None:
        raise SeparationError("demucs produced no vocal stem")

    return Separated(vocal_path=vocals, model=model, seconds=monotonic() - started)


def cleanup(separated: Separated) -> None:
    """Remove a separation's working directory once its stem has been analysed."""
    # <holding>/<model>/<track>/vocals.wav — remove the holding directory, not the stem.
    holding = separated.vocal_path.parent.parent.parent
    shutil.rmtree(holding, ignore_errors=True)
