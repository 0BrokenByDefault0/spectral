"""Check the RT60 estimate against rooms whose RT60 is known.

No corpus can validate the room measurement, because none is labelled with the room it
was recorded in. So this makes the labels: it takes real dry vocals and places them in
statistical rooms of known RT60 (exponentially decaying noise, Polack's model — the
standard for testing blind reverberation estimators, and the definition RT60 is written
against), then reports what the analysis measures.

    python -m tools.validate_room ~/corpus/ursing_vocals --pattern "*/Vocal.wav" --limit 8

The takes are real, so the singer's releases, consonants and vibrato are all present:
the confounds the measurement has to get past are the real ones.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import librosa
import numpy as np

from app.analysis import spectral

RT60S = (0.3, 0.6, 1.0, 1.5)


def room_impulse(rt60: float, sr: int, seed: int = 11) -> np.ndarray:
    """A statistical room: direct sound, then noise decaying 60 dB over `rt60` seconds."""
    samples = int(rt60 * 1.5 * sr)
    t = np.arange(samples) / sr
    tail = np.random.default_rng(seed).normal(0.0, 1.0, samples) * np.exp(-6.908 * t / rt60)
    tail[: int(0.002 * sr)] = 0.0  # nothing arrives in the first 2 ms but the direct path
    tail /= np.sqrt(np.sum(tail**2))
    tail[0] += 1.0  # equal direct and reverberant energy
    return tail


def place_in_room(y: np.ndarray, rt60: float, sr: int) -> np.ndarray:
    wet = np.convolve(y, room_impulse(rt60, sr))[: y.size]
    return (wet / (np.max(np.abs(wet)) + 1e-12) * 0.5).astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="validate_room", description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--pattern", default="*.wav")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--seconds", type=float, default=30.0)
    args = parser.parse_args(argv)

    files = sorted(args.corpus.glob(args.pattern))[: args.limit]
    if not files:
        print(f"no files matching {args.pattern} under {args.corpus}", file=sys.stderr)
        return 1

    rows: dict[float, list[float]] = {rt: [] for rt in RT60S}
    methods: dict[float, list[str]] = {rt: [] for rt in RT60S}
    dry: list[float] = []

    for path in files:
        y, sr = librosa.load(path, sr=spectral.SAMPLE_RATE, mono=True, duration=args.seconds)
        dry.append(spectral.analyze_samples(y, sr).room_quality.reverb_tail_ms / 1000.0)
        for rt60 in RT60S:
            room = spectral.analyze_samples(place_in_room(y, rt60, sr), sr).room_quality
            rows[rt60].append(room.reverb_tail_ms / 1000.0)
            methods[rt60].append(room.measurement)
        print(f"  measured {path.parent.name}/{path.name}", flush=True)

    print(f"\n{'true RT60':>10} {'median est':>11} {'IQR':>15} {'ratio':>7}  measured via")
    print(f"{'as-is':>10} {np.median(dry):11.2f}")
    for rt60 in RT60S:
        est = np.array(rows[rt60])
        q1, q3 = np.percentile(est, [25, 75])
        via = max(set(methods[rt60]), key=methods[rt60].count)
        print(
            f"{rt60:10.2f} {np.median(est):11.2f} {q1:7.2f}-{q3:<7.2f} "
            f"{np.median(est) / rt60:7.2f}  {via}"
        )

    medians = [np.median(rows[rt]) for rt in RT60S]
    monotonic = all(a < b for a, b in zip(medians, medians[1:]))
    print(f"\nordering preserved across rooms: {'yes' if monotonic else 'NO'}")
    return 0 if monotonic else 1


if __name__ == "__main__":
    raise SystemExit(main())
