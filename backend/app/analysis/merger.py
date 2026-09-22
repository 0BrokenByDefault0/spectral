"""Reconcile the spectral and qualitative passes into a single `VocalProfile`.

Rules of the merge:
- Measurements produce issues on their own, with solid but not total confidence —
  a number can be right about the signal and wrong about what matters.
- The listening pass produces issues on its own, with lower confidence — it is
  descriptive, not measured.
- When both passes name the same problem, confidence goes high and the worse of the
  two severities wins.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.spectral import BAND_LIMIT_HZ
from app.models.schemas import (
    ProcessingCategory,
    QualitativeAnalysis,
    Severity,
    SourceDetection,
    SpectralFeatures,
    VocalIssue,
    VocalProfile,
)

#: Confidence assigned by provenance.
CONFIDENCE_SPECTRAL_ONLY = 0.70
CONFIDENCE_QUALITATIVE_ONLY = 0.55
CONFIDENCE_AGREED = 0.95

_SEVERITY_ORDER = {Severity.MINOR: 0, Severity.MODERATE: 1, Severity.CRITICAL: 2}


@dataclass
class _Candidate:
    """A spectral issue plus the words that identify the same problem in prose."""

    name: str
    category: ProcessingCategory
    severity: Severity
    description: str
    evidence: dict
    tags: set[str] = field(default_factory=set)


def merge(
    spectral: SpectralFeatures,
    qualitative: QualitativeAnalysis | None,
    source: SourceDetection,
    genre: str | None = None,
    notes: list[str] | None = None,
) -> VocalProfile:
    """Build the unified profile the recommendation engine consumes."""
    candidates = derive_spectral_issues(spectral)
    issues = _reconcile(candidates, qualitative)

    all_notes = list(notes or [])
    bandwidth_note = _bandwidth_note(spectral)
    if bandwidth_note:
        all_notes.append(bandwidth_note)

    summary = qualitative.summary if qualitative else summarize(spectral, issues)
    return VocalProfile(
        source=source,
        bandwidth_hz=spectral.bandwidth_hz,
        frequency_bands=spectral.frequency_bands,
        dynamic_range=spectral.dynamic_range,
        noise_floor=spectral.noise_floor,
        room_quality=spectral.room_quality,
        pitch_stability=spectral.pitch_stability,
        sibilance=spectral.sibilance,
        issues=issues,
        qualitative_summary=summary,
        genre=genre,
        analysis_notes=all_notes,
    )


def _bandwidth_note(spectral: SpectralFeatures) -> str | None:
    """Say so when the source itself is the ceiling, and name the bands left unjudged.

    Real home recordings are often phone captures or lossy files that stop dead at 6-10
    kHz. Telling somebody to boost 8 kHz on a source that ends at 6 kHz is advice that
    can only add noise, so those bands are not scored and the real fix is named instead.
    """
    if spectral.bandwidth_hz >= BAND_LIMIT_HZ:
        return None

    unscored = [name for name, band in spectral.frequency_bands.items() if not band.scored]
    tail = f" The {', '.join(unscored)} band(s) were left unscored." if unscored else ""
    return (
        f"The source stops at about {spectral.bandwidth_hz / 1000:.1f} kHz — a phone "
        "recording, a lossy file, or a low sample rate somewhere in the chain. No EQ can "
        f"put back what was never captured; a better source is the fix.{tail}"
    )


# --- spectral issues -------------------------------------------------------


def derive_spectral_issues(spectral: SpectralFeatures) -> list[_Candidate]:
    """Turn measurements into named problems an engineer would recognise."""
    found: list[_Candidate] = []
    found.extend(_band_issues(spectral))
    found.extend(_sibilance_issues(spectral))
    found.extend(_dynamics_issues(spectral))
    found.extend(_noise_issues(spectral))
    found.extend(_room_issues(spectral))
    found.extend(_pitch_issues(spectral))
    return found


def _band_issues(spectral: SpectralFeatures) -> list[_Candidate]:
    issues: list[_Candidate] = []
    for name, rule in _BAND_RULES.items():
        band = spectral.frequency_bands.get(name)
        if band is None or not band.scored:
            continue
        for direction, label, tags, blurb in rule:
            deviation = band.deviation_db * direction
            if deviation < 3.0:
                continue
            issues.append(
                _Candidate(
                    name=label,
                    category=ProcessingCategory.EQ,
                    severity=band.severity,
                    description=(
                        f"{blurb} The {band.low_hz:.0f}-{band.high_hz:.0f} Hz band is "
                        f"{abs(band.deviation_db):.1f} dB "
                        f"{'above' if band.deviation_db > 0 else 'below'} a balanced vocal."
                    ),
                    evidence={
                        "band": name,
                        "deviation_db": round(band.deviation_db, 2),
                        "energy": round(band.energy, 4),
                    },
                    tags=tags,
                )
            )
    return issues


#: band -> (direction, issue name, matching tags, plain-language explanation)
_BAND_RULES: dict[str, list[tuple[int, str, set[str], str]]] = {
    "low_mid": [
        (
            1,
            "Low-Mid Buildup",
            {"mud", "muddy", "low-mid", "low mid", "boom", "thick", "cloudy"},
            "The vocal is carrying too much weight in the low mids, which reads as mud.",
        ),
        (
            -1,
            "Thin Body",
            {"thin", "weak", "no body", "lacks body", "hollow", "small"},
            "The vocal is short on body and will sit small against a busy track.",
        ),
    ],
    "boxiness": [
        (
            1,
            "Boxiness",
            {"box", "boxy", "honk", "nasal", "cardboard"},
            "There is a boxy, closed-in quality typical of an untreated recording space.",
        ),
    ],
    "presence": [
        (
            1,
            "Harsh Presence",
            {"harsh", "brittle", "edgy", "aggressive", "piercing", "shouty"},
            "The presence range is pushed hard enough to sound harsh on loud playback.",
        ),
        (
            -1,
            "Lacks Presence",
            {"dull", "veiled", "buried", "muffled", "lacks presence", "distant"},
            "The vocal lacks presence and will get buried by the instrumental.",
        ),
    ],
    "air": [
        (
            -1,
            "Lacks Air",
            {"dark", "dull", "no air", "lacks air", "closed", "muffled"},
            "The top end is closed off, so the vocal reads dark rather than open.",
        ),
    ],
}


def _sibilance_issues(spectral: SpectralFeatures) -> list[_Candidate]:
    sib = spectral.sibilance
    if sib.severity is Severity.MINOR:
        return []
    return [
        _Candidate(
            name="Sibilance",
            category=ProcessingCategory.DE_ESS,
            severity=sib.severity,
            description=(
                f"Ess and tee sounds are jumping forward, peaking around "
                f"{sib.peak_freq_hz:.0f} Hz."
            ),
            evidence={"ratio": round(sib.ratio, 4), "peak_freq_hz": round(sib.peak_freq_hz)},
            tags={"sibilance", "sibilant", "ess", "harsh s", "de-ess", "esses"},
        )
    ]


def _dynamics_issues(spectral: SpectralFeatures) -> list[_Candidate]:
    dyn = spectral.dynamic_range
    if not dyn.needs_compression:
        return []
    severity = (
        Severity.CRITICAL
        if dyn.loud_quiet_spread_db > 20.0 or dyn.crest_factor_db > 24.0
        else Severity.MODERATE
    )
    return [
        _Candidate(
            name="Uneven Dynamics",
            category=ProcessingCategory.COMPRESSION,
            severity=severity,
            description=(
                f"Level moves around by {dyn.loud_quiet_spread_db:.1f} dB between passages "
                f"(crest factor {dyn.crest_factor_db:.1f} dB), so quieter words will "
                "disappear under the track."
            ),
            evidence={
                "crest_factor_db": round(dyn.crest_factor_db, 2),
                "loud_quiet_spread_db": round(dyn.loud_quiet_spread_db, 2),
            },
            tags={"dynamic", "dynamics", "uneven", "inconsistent", "level", "jumps", "quiet"},
        )
    ]


def _noise_issues(spectral: SpectralFeatures) -> list[_Candidate]:
    noise = spectral.noise_floor
    issues: list[_Candidate] = []

    if noise.snr_db < 40.0:
        severity = (
            Severity.CRITICAL
            if noise.snr_db < 25.0
            else Severity.MODERATE
            if noise.snr_db < 33.0
            else Severity.MINOR
        )
        issues.append(
            _Candidate(
                name="Audible Noise Floor",
                category=ProcessingCategory.NOISE_REDUCTION,
                severity=severity,
                description=(
                    f"Signal-to-noise ratio is {noise.snr_db:.1f} dB, so room tone and preamp "
                    "hiss will be audible in the gaps."
                ),
                evidence={"snr_db": round(noise.snr_db, 2)},
                tags={"noise", "hiss", "background", "floor", "static", "air conditioning"},
            )
        )

    if noise.has_hum:
        issues.append(
            _Candidate(
                name="Mains Hum",
                category=ProcessingCategory.NOISE_REDUCTION,
                severity=Severity.MODERATE,
                description=(
                    f"A steady {noise.hum_freq_hz:.0f} Hz tone and its harmonics are present — "
                    "electrical hum from the interface or cabling."
                ),
                evidence={"hum_freq_hz": noise.hum_freq_hz},
                tags={"hum", "buzz", "electrical", "ground", "mains", "50hz", "60hz"},
            )
        )
    return issues


def _room_issues(spectral: SpectralFeatures) -> list[_Candidate]:
    room = spectral.room_quality
    if room.treated:
        return []
    return [
        _Candidate(
            name="Room Reflections",
            category=ProcessingCategory.NOISE_REDUCTION,
            severity=Severity.CRITICAL if room.reverb_tail_ms > 350.0 else Severity.MODERATE,
            description=(
                f"Roughly {room.reverb_tail_ms:.0f} ms of decay follows each phrase — the room "
                "is printed into the recording and will fight any reverb you add later."
            ),
            evidence={
                "reverb_tail_ms": round(room.reverb_tail_ms),
                "reflection_level": round(room.reflection_level, 2),
            },
            tags={"room", "reflection", "reverb", "roomy", "slap", "echo", "untreated", "live"},
        )
    ]


def _pitch_issues(spectral: SpectralFeatures) -> list[_Candidate]:
    pitch = spectral.pitch_stability
    if not pitch.needs_correction:
        return []
    return [
        _Candidate(
            name="Pitch Drift",
            category=ProcessingCategory.PITCH_CORRECTION,
            severity=Severity.CRITICAL if pitch.drift_cents > 60.0 else Severity.MODERATE,
            description=(
                f"Sustained notes wander by about {pitch.drift_cents:.0f} cents from their "
                "centre, which is enough to hear as out of tune."
            ),
            evidence={"drift_cents": round(pitch.drift_cents, 1)},
            tags={"pitch", "tuning", "tune", "flat", "sharp", "intonation", "off-key"},
        )
    ]


# --- reconciliation --------------------------------------------------------


def _reconcile(
    candidates: list[_Candidate], qualitative: QualitativeAnalysis | None
) -> list[VocalIssue]:
    remaining = list(candidates)
    issues: list[VocalIssue] = []

    for heard in qualitative.issues if qualitative else []:
        match = _find_match(heard, remaining)
        if match is None:
            issues.append(
                VocalIssue(
                    name=heard.name,
                    category=heard.category,
                    severity=heard.severity,
                    confidence=CONFIDENCE_QUALITATIVE_ONLY,
                    description=heard.description,
                    spectral_evidence=None,
                    sources=["qualitative"],
                )
            )
            continue

        remaining.remove(match)
        issues.append(
            VocalIssue(
                name=match.name,
                category=match.category,
                severity=_worse(match.severity, heard.severity),
                confidence=CONFIDENCE_AGREED,
                description=f"{match.description} Confirmed by ear: {heard.description}",
                spectral_evidence=match.evidence,
                sources=["spectral", "qualitative"],
            )
        )

    for candidate in remaining:
        issues.append(
            VocalIssue(
                name=candidate.name,
                category=candidate.category,
                severity=candidate.severity,
                confidence=CONFIDENCE_SPECTRAL_ONLY,
                description=candidate.description,
                spectral_evidence=candidate.evidence,
                sources=["spectral"],
            )
        )

    issues.sort(key=lambda i: (_SEVERITY_ORDER[i.severity], i.confidence), reverse=True)
    return issues


def _find_match(heard, candidates: list[_Candidate]) -> _Candidate | None:
    """Pair a described issue with a measured one.

    Same category is necessary but not sufficient — mud and harshness are both EQ
    problems, hum and mouth clicks are both noise problems — so the described text also
    has to mention one of the candidate's tags. Anything else stays a separate issue.
    """
    text = f"{heard.name} {heard.description}".lower()
    tagged = [
        c
        for c in candidates
        if c.category is heard.category and any(tag in text for tag in c.tags)
    ]
    if not tagged:
        return None
    return max(tagged, key=lambda c: sum(tag in text for tag in c.tags))


def _worse(a: Severity, b: Severity) -> Severity:
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b


# --- fallback summary ------------------------------------------------------


def summarize(spectral: SpectralFeatures, issues: list[VocalIssue]) -> str:
    """Plain-language summary used when the listening pass is unavailable."""
    if not issues:
        return (
            "No significant problems measured: the balance, dynamics and noise floor all "
            "sit in a normal range for a usable vocal take."
        )
    worst = issues[0]
    others = ", ".join(issue.name.lower() for issue in issues[1:4]) or "nothing else notable"
    return (
        f"Measured analysis only (no listening pass). The main problem is {worst.name.lower()}; "
        f"beyond that, {others}. "
        f"Signal-to-noise is {spectral.noise_floor.snr_db:.0f} dB and the crest factor is "
        f"{spectral.dynamic_range.crest_factor_db:.0f} dB."
    )
