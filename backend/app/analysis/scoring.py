"""Six 0-100 scores for the results radar chart.

These are presentation, not analysis — nothing downstream makes decisions from them.
They live here rather than in the frontend so the thresholds stay next to the constants
they are derived from: a score is just "how far is this from the value that would raise
an issue", and if those constants move, these move with them.

100 means nothing to fix; 0 means as bad as the analysis distinguishes.
"""

from __future__ import annotations

from app.analysis import spectral
from app.models.schemas import SpectralFeatures

#: The axes, in the order the radar draws them.
AXES = ("clarity", "dynamics", "noise", "room", "sibilance", "tonal_balance")


def score(features: SpectralFeatures) -> dict[str, float]:
    """Score each axis from the measurements behind it."""
    return {
        "clarity": _clarity(features),
        "dynamics": _dynamics(features),
        "noise": _noise(features),
        "room": _room(features),
        "sibilance": _sibilance(features),
        "tonal_balance": _tonal_balance(features),
    }


def _ramp(value: float, good: float, bad: float) -> float:
    """100 at `good`, 0 at `bad`, linear between, clamped outside."""
    if bad == good:
        return 100.0
    fraction = (value - good) / (bad - good)
    return float(round(max(0.0, min(1.0, 1.0 - fraction)) * 100.0, 1))


def _clarity(features: SpectralFeatures) -> float:
    """How well the vocal would cut through: presence, minus anything masking it."""
    presence = features.frequency_bands.get("presence")
    low_mid = features.frequency_bands.get("low_mid")

    shortfall = max(0.0, -presence.deviation_db) if presence and presence.scored else 0.0
    mask = max(0.0, low_mid.deviation_db) if low_mid and low_mid.scored else 0.0
    return _ramp(shortfall + mask, good=0.0, bad=spectral.BAND_CRITICAL_DB * 2)


def _dynamics(features: SpectralFeatures) -> float:
    dynamic = features.dynamic_range
    # Whichever of the two is worse relative to the point it would suggest compression.
    crest = dynamic.crest_factor_db / spectral.CREST_COMPRESSION_DB
    spread = dynamic.loud_quiet_spread_db / spectral.SPREAD_COMPRESSION_DB
    return _ramp(max(crest, spread), good=0.6, bad=2.0)


def _noise(features: SpectralFeatures) -> float:
    floor = features.noise_floor
    score = _ramp(-floor.snr_db, good=-60.0, bad=-20.0)
    if floor.has_hum:  # a tone in the gaps is more audible than its level suggests
        score = min(score, 50.0)
    return score


def _room(features: SpectralFeatures) -> float:
    return _ramp(
        features.room_quality.reverb_tail_ms,
        good=spectral.ROOM_TREATED_MS / 2,
        bad=spectral.ROOM_TREATED_MS * 4,
    )


def _sibilance(features: SpectralFeatures) -> float:
    return _ramp(
        features.sibilance.ratio,
        good=spectral.SIBILANCE_MODERATE / 2,
        bad=spectral.SIBILANCE_CRITICAL * 2,
    )


def _tonal_balance(features: SpectralFeatures) -> float:
    """Average distance from the reference, across the bands the source actually has."""
    scored = [band for band in features.frequency_bands.values() if band.scored]
    if not scored:
        return 100.0
    average = sum(abs(band.deviation_db) for band in scored) / len(scored)
    return _ramp(average, good=0.0, bad=spectral.BAND_CRITICAL_DB)
