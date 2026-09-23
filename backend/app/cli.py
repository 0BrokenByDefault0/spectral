"""CLI: analyse a recording, then print the profile and the three plugin chains.

    python -m app.cli take.wav --genre "bedroom rap"
    python -m app.cli take.wav --no-llm --json result.json
    python -m app.cli take.wav --tier FREE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.analysis import spectral
from app.analysis.pipeline import analyze_file
from app.db.repository import CatalogUnavailableError, PluginCatalog
from app.models.schemas import AnalysisResult, SignalChain, Tier, VocalProfile
from app.recommendation.chain_builder import build_chains

_BAR_WIDTH = 24


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voxchain", description="Analyse a vocal recording")
    parser.add_argument("audio", type=Path, help="Path to a WAV/FLAC/MP3 recording")
    parser.add_argument("--genre", help="Genre tag, used as context for the listening pass")
    parser.add_argument(
        "--no-llm", action="store_true", help="Skip the Gemini listening pass entirely"
    )
    parser.add_argument(
        "--tier",
        type=str.upper,
        choices=[tier.value for tier in Tier],
        help="Only build the chain for this tier (default: all three)",
    )
    parser.add_argument(
        "--no-separate",
        action="store_true",
        help="Analyse a full mix as-is instead of isolating the vocal first",
    )
    parser.add_argument("--no-chains", action="store_true", help="Analysis only, no chains")
    parser.add_argument("--json", type=Path, help="Also write the full result as JSON here")
    args = parser.parse_args(argv)

    if not args.audio.exists():
        print(f"no such file: {args.audio}", file=sys.stderr)
        return 2

    try:
        profile = analyze_file(
            args.audio,
            genre=args.genre,
            use_llm=not args.no_llm,
            separate=not args.no_separate,
        )
    except spectral.AudioTooShortError as exc:
        print(f"cannot analyse: {exc}", file=sys.stderr)
        return 1

    chains: list[SignalChain] = []
    if not args.no_chains:
        tiers = (Tier(args.tier),) if args.tier else (Tier.FREE, Tier.MID, Tier.PREMIUM)
        try:
            chains = build_chains(profile, PluginCatalog.load(), tiers=tiers)
        except CatalogUnavailableError as exc:
            print(f"skipping chains: {exc}", file=sys.stderr)

    print(render(profile, args.audio))
    for chain in chains:
        print()
        print(render_chain(chain))

    if args.json:
        result = AnalysisResult(profile=profile, chains=chains)
        args.json.write_text(result.model_dump_json(indent=2))
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
        f"room RT60         "
        + (
            f"{room.reverb_tail_ms / 1000:.2f} s ({'treated' if room.treated else 'live'}, "
            f"from {room.probes} {room.measurement})"
            if room.measurement != "none"
            else "not measurable in this take"
        ),
        f"pitch drift       {pitch.drift_cents:.0f} cents "
        f"(voiced {pitch.voiced_ratio:.0%})",
        f"sibilance         ratio {sib.ratio:.3f} peaking at {sib.peak_freq_hz:.0f} Hz",
        f"source bandwidth  {profile.bandwidth_hz / 1000:.1f} kHz",
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


def render_chain(chain: SignalChain) -> str:
    """Format one tier's signal chain, in signal order."""
    # A plugin used twice in a chain is bought once.
    total = sum(_price_of(price) for price in {s.plugin_name: s.price for s in chain.steps}.values())
    lines = [
        f"--- {chain.tier.value} chain ({len(chain.steps)} steps, "
        f"{'free' if total == 0 else f'about ${total:.0f} to buy outright'}) ---",
        " → ".join(step.plugin_name for step in chain.steps),
        "",
    ]
    for position, step in enumerate(chain.steps, start=1):
        lines.append(f"{position}. {step.plugin_name} [{step.category.value}] {step.price}")
        lines.append(f"   {step.suggested_settings}")
        lines.append(f"   why: {step.why}")
        if step.purchase_url:
            lines.append(f"   {step.purchase_url}")
    return "\n".join(lines)


def _price_of(price: str) -> float:
    """Pull a number out of a display price like '$49' or 'Free (ReaPlugs)'."""
    digits = "".join(c for c in price if c.isdigit() or c == ".")
    try:
        return float(digits)
    except ValueError:
        return 0.0


def _bar(deviation_db: float, span_db: float = 12.0) -> str:
    """A centred bar showing how far a band sits from the reference."""
    half = _BAR_WIDTH // 2
    steps = int(round(max(-span_db, min(span_db, deviation_db)) / span_db * half))
    if steps >= 0:
        return " " * half + "#" * steps
    return " " * (half + steps) + "#" * -steps


if __name__ == "__main__":
    raise SystemExit(main())
