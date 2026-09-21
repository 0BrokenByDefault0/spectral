"""Phase 1 CLI: analyse a recording and print the profile.

    python -m app.cli take.wav --genre "bedroom rap"
    python -m app.cli take.wav --no-llm --json profile.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.analysis import spectral
from app.analysis.pipeline import analyze_file
from app.models.schemas import VocalProfile

_BAR_WIDTH = 24


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voxchain", description="Analyse a vocal recording")
    parser.add_argument("audio", type=Path, help="Path to a WAV/FLAC/MP3 recording")
    parser.add_argument("--genre", help="Genre tag, used as context for the listening pass")
    parser.add_argument(
        "--no-llm", action="store_true", help="Skip the Gemini listening pass entirely"
    )
    parser.add_argument("--json", type=Path, help="Also write the full profile as JSON here")
    args = parser.parse_args(argv)

    if not args.audio.exists():
        print(f"no such file: {args.audio}", file=sys.stderr)
        return 2

    try:
        profile = analyze_file(args.audio, genre=args.genre, use_llm=not args.no_llm)
    except spectral.AudioTooShortError as exc:
        print(f"cannot analyse: {exc}", file=sys.stderr)
        return 1

    print(render(profile, args.audio))
    if args.json:
        args.json.write_text(profile.model_dump_json(indent=2))
        print(f"\nwrote {args.json}")
    return 0


def render(profile: VocalProfile, audio: Path) -> str:
    """Format a profile for a terminal."""
    lines = [
        f"=== {audio.name} ===",
        f"source      {profile.source.source_type.value} "
        f"(confidence {profile.source.confidence:.0%})",
        f"            {'; '.join(profile.source.reasons)}",
        "",
        "--- summary ---",
        profile.qualitative_summary,
        "",
        "--- frequency balance (vs. reference vocal) ---",
    ]

    for name, band in profile.frequency_bands.items():
        lines.append(
            f"{name:<11} {band.low_hz / 1000:>5.1f}-{band.high_hz / 1000:<5.1f}kHz  "
            f"{band.deviation_db:+6.1f} dB  {_bar(band.deviation_db)}"
        )

    dyn, noise, room, pitch, sib = (
        profile.dynamic_range,
        profile.noise_floor,
        profile.room_quality,
        profile.pitch_stability,
        profile.sibilance,
    )
    lines += [
        "",
        "--- measurements ---",
        f"crest factor      {dyn.crest_factor_db:.1f} dB "
        f"(passage spread {dyn.loud_quiet_spread_db:.1f} dB)",
        f"signal-to-noise   {noise.snr_db:.1f} dB"
        + (f", hum at {noise.hum_freq_hz:.0f} Hz" if noise.has_hum else "")
        + (", broadband noise" if noise.has_broadband else ""),
        f"room tail         {room.reverb_tail_ms:.0f} ms "
        f"({'treated' if room.treated else 'live'})",
        f"pitch drift       {pitch.drift_cents:.0f} cents "
        f"(voiced {pitch.voiced_ratio:.0%})",
        f"sibilance         ratio {sib.ratio:.3f} peaking at {sib.peak_freq_hz:.0f} Hz",
        "",
        f"--- issues ({len(profile.issues)}) ---",
    ]

    if not profile.issues:
        lines.append("none detected")
    for issue in profile.issues:
        lines.append(
            f"[{issue.severity.value:<8}] {issue.name} "
            f"({issue.category.value}, confidence {issue.confidence:.0%}, "
            f"{'+'.join(issue.sources)})"
        )
        lines.append(f"           {issue.description}")

    if profile.analysis_notes:
        lines += ["", "--- notes ---", *(f"* {note}" for note in profile.analysis_notes)]
    return "\n".join(lines)


def _bar(deviation_db: float, span_db: float = 12.0) -> str:
    """A centred bar showing how far a band sits from the reference."""
    half = _BAR_WIDTH // 2
    steps = int(round(max(-span_db, min(span_db, deviation_db)) / span_db * half))
    if steps >= 0:
        return " " * half + "#" * steps
    return " " * (half + steps) + "#" * -steps


if __name__ == "__main__":
    raise SystemExit(main())
