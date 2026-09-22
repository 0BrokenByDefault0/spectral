"""Measure a corpus of real recordings and propose constants from what comes back.

The reference constants in `app/analysis/spectral.py` decide what counts as a problem,
so they have to come from recordings rather than from taste. This tool runs the spectral
analysis over a labelled corpus, writes one JSON line per file, and then reports what the
distributions say the constants should be.

    python -m tools.calibrate measure ~/corpus/VocalSet --label vocalset --out runs.jsonl
    python -m tools.calibrate report runs.jsonl
    python -m tools.calibrate propose runs.jsonl --reference vocalset --home vocadito

`measure` appends, so several corpora accumulate in one file. Sampling is deterministic:
the same `--limit` over the same directory always picks the same files.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from app.analysis import detector, spectral
from app.models.schemas import SourceType

AUDIO_SUFFIXES = {".wav", ".flac", ".mp3", ".aiff", ".aif", ".ogg", ".m4a"}

#: Percentiles reported for every metric, and used to propose thresholds.
PERCENTILES = (5, 25, 50, 75, 90, 95, 99)


# --- measuring -------------------------------------------------------------


def find_audio(root: Path, limit: int | None, seed: int = 7) -> list[Path]:
    """Audio files under `root`, sampled deterministically when `limit` is set."""
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in AUDIO_SUFFIXES)
    if limit is not None and len(files) > limit:
        files = sorted(random.Random(seed).sample(files, limit))
    return files


def measure_one(job: tuple[Path, float | None]) -> dict | None:
    """Every metric for one file, flattened. `None` if the file cannot be used."""
    path, max_seconds = job
    try:
        y, sr = spectral.load_audio(str(path))
        if max_seconds is not None:
            # A full track costs minutes of pitch tracking for no extra information, and
            # the first minute is closer to what somebody actually uploads.
            y = y[: int(max_seconds * sr)]
        features = spectral.analyze_samples(y, sr)
        source = detector.detect_samples(y, sr)
    except spectral.AudioTooShortError:
        return None
    except Exception as exc:  # a corpus always contains one unreadable file
        print(f"  skipped {path.name}: {exc}", file=sys.stderr)
        return None

    record = {
        "path": str(path),
        "duration_s": round(features.duration_s, 2),
        "bandwidth_hz": features.bandwidth_hz,
        "crest_factor_db": features.dynamic_range.crest_factor_db,
        "loud_quiet_spread_db": features.dynamic_range.loud_quiet_spread_db,
        "snr_db": features.noise_floor.snr_db,
        "has_hum": features.noise_floor.has_hum,
        "has_broadband": features.noise_floor.has_broadband,
        "reverb_tail_ms": features.room_quality.reverb_tail_ms,
        "drift_cents": features.pitch_stability.drift_cents,
        "voiced_ratio": features.pitch_stability.voiced_ratio,
        "sibilance_ratio": features.sibilance.ratio,
        "sibilance_peak_hz": features.sibilance.peak_freq_hz,
        "sub_bass_ratio": source.sub_bass_ratio,
        "percussive_ratio": source.percussive_ratio,
        "onset_rate_hz": source.onset_rate_hz,
        "detected": source.source_type.value,
    }
    for name, band in features.frequency_bands.items():
        record[f"energy_{name}"] = band.energy
    return record


def measure(args: argparse.Namespace) -> int:
    files = find_audio(args.corpus, args.limit)
    if not files:
        print(f"no audio under {args.corpus}", file=sys.stderr)
        return 1

    print(f"measuring {len(files)} files from {args.corpus} as '{args.label}'")
    written = 0
    with args.out.open("a") as sink, ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [(path, args.max_seconds) for path in files]
        for index, record in enumerate(pool.map(measure_one, jobs, chunksize=4), start=1):
            if record is None:
                continue
            record["label"] = args.label
            sink.write(json.dumps(record) + "\n")
            written += 1
            if index % 25 == 0:
                print(f"  {index}/{len(files)}", flush=True)

    print(f"wrote {written} measurements to {args.out}")
    return 0


# --- reporting -------------------------------------------------------------


def load_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def by_label(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["label"], []).append(record)
    return grouped


def column(records: list[dict], key: str) -> np.ndarray:
    return np.array([r[key] for r in records if isinstance(r.get(key), (int, float))], dtype=float)


REPORT_METRICS = (
    "duration_s",
    "bandwidth_hz",
    "crest_factor_db",
    "loud_quiet_spread_db",
    "snr_db",
    "reverb_tail_ms",
    "drift_cents",
    "voiced_ratio",
    "sibilance_ratio",
    "sub_bass_ratio",
    "percussive_ratio",
    "onset_rate_hz",
    "energy_low_mid",
    "energy_boxiness",
    "energy_presence",
    "energy_air",
    "energy_ultra_high",
)


def report(args: argparse.Namespace) -> int:
    grouped = by_label(load_records(args.runs))
    for label, records in sorted(grouped.items()):
        print(f"\n=== {label} ({len(records)} files) ===")
        header = "metric".ljust(22) + "".join(f"p{p}".rjust(11) for p in PERCENTILES)
        print(header)
        for metric in REPORT_METRICS:
            values = column(records, metric)
            if values.size == 0:
                continue
            cells = "".join(f"{np.percentile(values, p):11.4g}" for p in PERCENTILES)
            print(metric.ljust(22) + cells)

        hum = sum(1 for r in records if r.get("has_hum"))
        mixes = sum(1 for r in records if r.get("detected") == SourceType.FULL_MIX.value)
        print(
            f"{'flags'.ljust(22)}hum {hum}/{len(records)}, "
            f"detected as full mix {mixes}/{len(records)}"
        )
    return 0


# --- proposing constants ---------------------------------------------------


def propose(args: argparse.Namespace) -> int:
    grouped = by_label(load_records(args.runs))
    reference = grouped.get(args.reference)
    if not reference:
        print(f"no records labelled '{args.reference}' in {args.runs}", file=sys.stderr)
        return 1

    print(f"# Proposed from {len(reference)} '{args.reference}' recordings\n")
    _propose_balance(reference)
    _propose_band_thresholds(reference)
    _propose_sibilance(reference)
    if args.home:
        _propose_room(reference, grouped.get(args.home, []), args.reference, args.home)
    _propose_dynamics(reference)
    _propose_pitch(reference)
    if args.mix:
        _propose_detector(grouped, args.mix)
    return 0


def _propose_balance(reference: list[dict]) -> None:
    print("REFERENCE_BALANCE = {")
    for band in spectral.BANDS:
        values = column(reference, f"energy_{band}")
        current = spectral.REFERENCE_BALANCE[band]
        median = float(np.median(values))
        shift = 10 * np.log10(median / current)
        print(f'    "{band}": {median:.4f},'.ljust(34) + f"# was {current:.4f} ({shift:+.1f} dB)")
    print("}\n")


def _propose_band_thresholds(reference: list[dict]) -> None:
    """Severity thresholds from how much good takes vary around their own median."""
    spreads = []
    for band in spectral.BANDS:
        values = column(reference, f"energy_{band}")
        median = np.median(values)
        deviations = np.abs(10 * np.log10(values / median))
        spreads.append((band, np.percentile(deviations, 75), np.percentile(deviations, 95)))

    moderate = float(np.median([s[1] for s in spreads]))
    critical = float(np.median([s[2] for s in spreads]))
    print(f"BAND_MODERATE_DB = {moderate:.1f}   # was {spectral.BAND_MODERATE_DB}")
    print(f"BAND_CRITICAL_DB = {critical:.1f}   # was {spectral.BAND_CRITICAL_DB}")
    print("# per-band |deviation from the reference median|, in dB:")
    for band, p75, p95 in spreads:
        print(f"#   {band:<12} p75 {p75:5.1f}  p95 {p95:5.1f}")
    print()


def _propose_sibilance(reference: list[dict]) -> None:
    values = column(reference, "sibilance_ratio")
    moderate, critical = np.percentile(values, [85, 97])
    print(f"SIBILANCE_MODERATE = {moderate:.3f}   # was {spectral.SIBILANCE_MODERATE}")
    print(f"SIBILANCE_CRITICAL = {critical:.3f}   # was {spectral.SIBILANCE_CRITICAL}")
    print(f"# good takes: median {np.median(values):.3f}, p99 {np.percentile(values, 99):.3f}\n")


def _propose_room(
    reference: list[dict], home: list[dict], reference_label: str, home_label: str
) -> None:
    """Pick the tail threshold that best separates treated from untreated rooms."""
    treated = column(reference, "reverb_tail_ms")
    untreated = column(home, "reverb_tail_ms")
    if treated.size == 0 or untreated.size == 0:
        print(f"# no room comparison: need both '{reference_label}' and '{home_label}'\n")
        return

    candidates = np.unique(np.concatenate([treated, untreated]))
    best, best_score = spectral.ROOM_TREATED_MS, -1.0
    for threshold in candidates:
        correct = (treated < threshold).sum() + (untreated >= threshold).sum()
        score = correct / (treated.size + untreated.size)
        if score > best_score:
            best, best_score = float(threshold), float(score)

    print(f"ROOM_TREATED_MS = {best:.0f}   # was {spectral.ROOM_TREATED_MS}")
    print(
        f"# separates {reference_label} (median {np.median(treated):.0f} ms) from "
        f"{home_label} (median {np.median(untreated):.0f} ms) "
        f"at {best_score:.0%} accuracy\n"
    )


def _propose_dynamics(reference: list[dict]) -> None:
    crest = column(reference, "crest_factor_db")
    spread = column(reference, "loud_quiet_spread_db")
    print(f"CREST_COMPRESSION_DB = {np.percentile(crest, 75):.1f}   # was {spectral.CREST_COMPRESSION_DB}")
    print(
        f"SPREAD_COMPRESSION_DB = {np.percentile(spread, 75):.1f}   "
        f"# was {spectral.SPREAD_COMPRESSION_DB}"
    )
    print(f"# good takes: crest median {np.median(crest):.1f} dB, spread median {np.median(spread):.1f} dB\n")


def _propose_pitch(reference: list[dict]) -> None:
    drift = column(reference, "drift_cents")
    print(f"PITCH_CORRECTION_CENTS = {np.percentile(drift, 90):.0f}   # was {spectral.PITCH_CORRECTION_CENTS}")
    print(f"# good takes: drift median {np.median(drift):.0f} cents, p99 {np.percentile(drift, 99):.0f}\n")


def _propose_detector(grouped: dict[str, list[dict]], mix_label: str) -> None:
    """Score the detector against labelled vocals and mixes."""
    mixes = grouped.get(mix_label, [])
    vocals = [r for label, rs in grouped.items() if label != mix_label for r in rs]
    if not mixes or not vocals:
        print(f"# no detector scoring: need records labelled '{mix_label}'\n")
        return

    mix_hits = sum(1 for r in mixes if r["detected"] == SourceType.FULL_MIX.value)
    vocal_hits = sum(1 for r in vocals if r["detected"] == SourceType.DRY_VOCAL.value)
    print("# detector, as currently tuned:")
    print(f"#   mixes  identified {mix_hits}/{len(mixes)} ({mix_hits / len(mixes):.0%})")
    print(f"#   vocals identified {vocal_hits}/{len(vocals)} ({vocal_hits / len(vocals):.0%})")

    for metric, constant in (
        ("sub_bass_ratio", detector.SUB_BASS_MIX),
        ("percussive_ratio", detector.PERCUSSIVE_MIX),
        ("onset_rate_hz", detector.ONSET_RATE_MIX),
    ):
        mix_values = column(mixes, metric)
        vocal_values = column(vocals, metric)
        best, best_score = constant, -1.0
        for threshold in np.unique(np.concatenate([mix_values, vocal_values])):
            correct = (mix_values > threshold).sum() + (vocal_values <= threshold).sum()
            score = correct / (mix_values.size + vocal_values.size)
            if score > best_score:
                best, best_score = float(threshold), float(score)
        print(
            f"#   {metric:<17} vocals p95 {np.percentile(vocal_values, 95):7.3f}  "
            f"mixes p5 {np.percentile(mix_values, 5):7.3f}  "
            f"best split {best:.3f} ({best_score:.0%}), currently {constant}"
        )
    print()


# --- entry point -----------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="calibrate", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("measure", help="Measure every recording in a corpus")
    run.add_argument("corpus", type=Path)
    run.add_argument("--label", required=True, help="Corpus name, e.g. vocalset")
    run.add_argument("--out", type=Path, default=Path("runs.jsonl"))
    run.add_argument("--limit", type=int, help="Sample this many files (deterministic)")
    run.add_argument("--workers", type=int, default=4)
    run.add_argument(
        "--max-seconds",
        type=float,
        default=60.0,
        help="Analyse only the first N seconds of each file (default 60)",
    )
    run.set_defaults(func=measure)

    show = sub.add_parser("report", help="Percentile tables per corpus")
    show.add_argument("runs", type=Path)
    show.set_defaults(func=report)

    suggest = sub.add_parser("propose", help="Propose constants from the measurements")
    suggest.add_argument("runs", type=Path)
    suggest.add_argument("--reference", required=True, help="Label of the good-takes corpus")
    suggest.add_argument("--home", help="Label of the untreated-room corpus")
    suggest.add_argument("--mix", help="Label of the full-mix corpus")
    suggest.set_defaults(func=propose)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
