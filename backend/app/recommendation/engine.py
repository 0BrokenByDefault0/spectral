"""Turn a `VocalProfile` into the processing steps the vocal actually needs.

This module decides *what* processing the take needs and *how to set it*, from the
measured evidence. `chain_builder.py` decides which plugin fills each step at each
price tier. Keeping those apart means the advice does not change when the catalog does.

One step per role: an engineer does every subtractive cut in one EQ instance, so the
issues that call for cuts merge into a single step with combined settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.models.schemas import (
    ProcessingCategory,
    Severity,
    VocalIssue,
    VocalProfile,
)

_SEVERITY_ORDER = {Severity.MINOR: 0, Severity.MODERATE: 1, Severity.CRITICAL: 2}


class StepRole(str, Enum):
    """A slot in the signal chain. Order lives in `chain_builder.py`."""

    NOISE_REDUCTION = "NOISE_REDUCTION"
    GATE = "GATE"
    PITCH = "PITCH"
    SUBTRACTIVE_EQ = "SUBTRACTIVE_EQ"
    COMPRESSION = "COMPRESSION"
    ADDITIVE_EQ = "ADDITIVE_EQ"
    DE_ESS = "DE_ESS"
    SATURATION = "SATURATION"
    SPATIAL = "SPATIAL"
    LIMITER = "LIMITER"


#: Human-readable label for each slot, used in the chain diagram and CLI.
ROLE_LABELS: dict[StepRole, str] = {
    StepRole.NOISE_REDUCTION: "Clean up",
    StepRole.GATE: "Gate",
    StepRole.PITCH: "Tuning",
    StepRole.SUBTRACTIVE_EQ: "Corrective EQ",
    StepRole.COMPRESSION: "Compression",
    StepRole.ADDITIVE_EQ: "Tone EQ",
    StepRole.DE_ESS: "De-ess",
    StepRole.SATURATION: "Saturation",
    StepRole.SPATIAL: "Space",
    StepRole.LIMITER: "Peak control",
}

#: Tags that disqualify a plugin from a role. A boost slot cannot be filled by a
#: processor that only ever reduces, however good it is.
_ROLE_EXCLUDED_TAGS: dict[StepRole, tuple[str, ...]] = {
    StepRole.ADDITIVE_EQ: ("cut-only",),
}

#: Roles where the same plugin may appear twice in one chain. Engineers open a second
#: EQ instance rather than buying a second EQ, so forcing a different brand into the
#: tone slot would recommend a worse tool for no reason.
_REUSABLE_ROLES: frozenset[StepRole] = frozenset({StepRole.SUBTRACTIVE_EQ, StepRole.ADDITIVE_EQ})

_ROLE_CATEGORY: dict[StepRole, ProcessingCategory] = {
    StepRole.NOISE_REDUCTION: ProcessingCategory.NOISE_REDUCTION,
    StepRole.GATE: ProcessingCategory.GATE,
    StepRole.PITCH: ProcessingCategory.PITCH_CORRECTION,
    StepRole.SUBTRACTIVE_EQ: ProcessingCategory.EQ,
    StepRole.COMPRESSION: ProcessingCategory.COMPRESSION,
    StepRole.ADDITIVE_EQ: ProcessingCategory.EQ,
    StepRole.DE_ESS: ProcessingCategory.DE_ESS,
    StepRole.SATURATION: ProcessingCategory.SATURATION,
    StepRole.SPATIAL: ProcessingCategory.REVERB,
    StepRole.LIMITER: ProcessingCategory.LIMITER,
}

#: Where a qualitative-only issue lands when there is no measurement behind it.
_CATEGORY_ROLE: dict[ProcessingCategory, StepRole] = {
    ProcessingCategory.EQ: StepRole.SUBTRACTIVE_EQ,
    ProcessingCategory.COMPRESSION: StepRole.COMPRESSION,
    ProcessingCategory.DE_ESS: StepRole.DE_ESS,
    ProcessingCategory.SATURATION: StepRole.SATURATION,
    ProcessingCategory.GATE: StepRole.GATE,
    ProcessingCategory.NOISE_REDUCTION: StepRole.NOISE_REDUCTION,
    ProcessingCategory.PITCH_CORRECTION: StepRole.PITCH,
    ProcessingCategory.REVERB: StepRole.SPATIAL,
    ProcessingCategory.DELAY: StepRole.SPATIAL,
    ProcessingCategory.LIMITER: StepRole.LIMITER,
}


@dataclass
class ProcessingStep:
    """One slot in the chain, with everything needed to fill and explain it."""

    role: StepRole
    severity: Severity = Severity.MINOR
    settings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    preferred_tags: tuple[str, ...] = ()

    @property
    def category(self) -> ProcessingCategory:
        return _ROLE_CATEGORY[self.role]

    @property
    def label(self) -> str:
        return ROLE_LABELS[self.role]

    @property
    def excluded_tags(self) -> tuple[str, ...]:
        return _ROLE_EXCLUDED_TAGS.get(self.role, ())

    @property
    def allows_reuse(self) -> bool:
        return self.role in _REUSABLE_ROLES

    def settings_text(self) -> str:
        return " Then: ".join(self.settings)

    def reason_text(self) -> str:
        return " ".join(self.reasons)


def plan(profile: VocalProfile) -> list[ProcessingStep]:
    """The processing this take needs, one step per role, worst issue first."""
    steps: dict[StepRole, ProcessingStep] = {}

    for issue in profile.issues:
        for partial in _steps_for_issue(issue, profile):
            _absorb(steps, partial)

    for partial in _baseline_steps(profile, steps):
        _absorb(steps, partial)

    return list(steps.values())


def _absorb(steps: dict[StepRole, ProcessingStep], new: ProcessingStep) -> None:
    """Merge a step into the role it belongs to, keeping the worst severity."""
    existing = steps.get(new.role)
    if existing is None:
        steps[new.role] = new
        return
    existing.settings.extend(new.settings)
    existing.reasons.extend(new.reasons)
    existing.issues.extend(new.issues)
    existing.preferred_tags = tuple(dict.fromkeys(existing.preferred_tags + new.preferred_tags))
    if _SEVERITY_ORDER[new.severity] > _SEVERITY_ORDER[existing.severity]:
        existing.severity = new.severity


# --- per-issue rules -------------------------------------------------------


def _steps_for_issue(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    builder = _ISSUE_BUILDERS.get(issue.name)
    if builder is not None:
        return builder(issue, profile)
    return [_generic_step(issue)]


def _generic_step(issue: VocalIssue) -> ProcessingStep:
    """Fallback for an issue only the listening pass raised: no numbers to work from."""
    return ProcessingStep(
        role=_CATEGORY_ROLE[issue.category],
        severity=issue.severity,
        settings=[
            "Set by ear — this came from the listening pass, so there is no measurement "
            "to derive a starting point from."
        ],
        reasons=[issue.description],
        issues=[issue.name],
    )


def _evidence(issue: VocalIssue, key: str, default: float) -> float:
    value = (issue.spectral_evidence or {}).get(key, default)
    return float(value) if isinstance(value, (int, float)) else default


def _cut_db(deviation_db: float, floor: float = 2.0, ceiling: float = 6.0) -> float:
    """How much to cut: follow the measurement, but never more than 6 dB in one bell."""
    return min(max(abs(deviation_db), floor), ceiling)


def _low_mid_buildup(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    cut = _cut_db(_evidence(issue, "deviation_db", 3.0))
    return [
        ProcessingStep(
            role=StepRole.SUBTRACTIVE_EQ,
            severity=issue.severity,
            settings=[
                "High-pass at 80 Hz (24 dB/oct), then a wide bell (Q 1.0) of "
                f"-{cut:.1f} dB somewhere in 200-500 Hz — sweep with a narrow boost first "
                "to find the worst spot, then widen and cut there"
            ],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("surgical", "transparent"),
        )
    ]


def _boxiness(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    cut = _cut_db(_evidence(issue, "deviation_db", 3.0), ceiling=5.0)
    return [
        ProcessingStep(
            role=StepRole.SUBTRACTIVE_EQ,
            severity=issue.severity,
            settings=[f"-{cut:.1f} dB bell at Q 2.0, centred 900 Hz-1 kHz"],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("surgical", "dynamic"),
        )
    ]


def _thin_body(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    boost = _cut_db(_evidence(issue, "deviation_db", 3.0), ceiling=4.0)
    return [
        ProcessingStep(
            role=StepRole.ADDITIVE_EQ,
            severity=issue.severity,
            settings=[f"+{boost:.1f} dB wide bell (Q 0.8) at 220-280 Hz"],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("character", "warmth"),
        ),
        ProcessingStep(
            role=StepRole.SATURATION,
            severity=Severity.MINOR,
            settings=[
                "Drive for 1-2 dB of thickening and no more; match levels and A/B, because "
                "saturation always sounds better simply because it is louder"
            ],
            reasons=["Harmonics add perceived body that EQ alone cannot."],
            issues=[issue.name],
            preferred_tags=("warmth", "character"),
        ),
    ]


def _harsh_presence(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    cut = _cut_db(_evidence(issue, "deviation_db", 3.0), ceiling=5.0)
    return [
        ProcessingStep(
            role=StepRole.SUBTRACTIVE_EQ,
            severity=issue.severity,
            settings=[
                f"Dynamic band of up to -{cut:.1f} dB at Q 2.0 over 2.5-4 kHz, threshold set "
                "so it only moves on the loud words — a static cut here makes the vocal dull"
            ],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("dynamic", "resonance", "harshness"),
        )
    ]


def _lacks_presence(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    boost = _cut_db(_evidence(issue, "deviation_db", 3.0), ceiling=4.0)
    return [
        ProcessingStep(
            role=StepRole.ADDITIVE_EQ,
            severity=issue.severity,
            settings=[f"+{boost:.1f} dB bell (Q 0.7) at 3 kHz"],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("character", "presence"),
        ),
        ProcessingStep(
            role=StepRole.SATURATION,
            severity=Severity.MINOR,
            settings=[
                "Light drive to generate upper harmonics — this cuts through a busy track "
                "where a presence boost alone just raises the noise with it"
            ],
            reasons=["Saturation buys presence without lifting the noise floor as much as EQ."],
            issues=[issue.name],
            preferred_tags=("presence", "character"),
        ),
    ]


def _lacks_air(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    boost = _cut_db(_evidence(issue, "deviation_db", 3.0), ceiling=4.0)
    tail = ["High shelf of +%.1f dB from 8 kHz" % boost]
    if profile.noise_floor.snr_db < 35.0:
        tail.append(
            f"keep the shelf gentle: at {profile.noise_floor.snr_db:.0f} dB SNR it lifts hiss "
            "as fast as it lifts air, so de-noise first"
        )
    return [
        ProcessingStep(
            role=StepRole.ADDITIVE_EQ,
            severity=issue.severity,
            settings=[" — ".join(tail)],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("character", "transparent"),
        )
    ]


def _sibilance(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    peak = _evidence(issue, "peak_freq_hz", profile.sibilance.peak_freq_hz)
    reduction = 6.0 if issue.severity is Severity.CRITICAL else 3.0
    return [
        ProcessingStep(
            role=StepRole.DE_ESS,
            severity=issue.severity,
            settings=[
                f"Centre the detector on {peak:.0f} Hz, split-band mode, threshold so it "
                f"only engages on esses, up to {reduction:.0f} dB reduction. Listen to the "
                "band on its own: if you hear words, the band is too wide"
            ],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("split-band", "transparent", "adaptive"),
        )
    ]


def _uneven_dynamics(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    spread = _evidence(issue, "loud_quiet_spread_db", profile.dynamic_range.loud_quiet_spread_db)
    ratio = "4:1" if issue.severity is Severity.CRITICAL else "3:1"
    settings = [
        f"Ratio {ratio}, attack 5-10 ms, release 60-120 ms, threshold for 4-6 dB of gain "
        f"reduction on the loudest words (the take swings by {spread:.0f} dB)"
    ]
    if spread > 18.0:
        settings.append(
            "With this much swing, use two gentle stages (or ride the fader first) rather "
            "than one compressor working hard — 10 dB of reduction in one place breathes"
        )
    return [
        ProcessingStep(
            role=StepRole.COMPRESSION,
            severity=issue.severity,
            settings=settings,
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("leveling", "transparent", "peaks"),
        )
    ]


def _noise_floor(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    snr = _evidence(issue, "snr_db", profile.noise_floor.snr_db)
    amount = 6.0 if snr > 30.0 else 10.0
    steps = [
        ProcessingStep(
            role=StepRole.NOISE_REDUCTION,
            severity=issue.severity,
            settings=[
                f"Learn the noise profile from a gap between phrases and reduce by about "
                f"{amount:.0f} dB. Past that you will hear the vocal thin out and the "
                "consonants smear, so stop there and gate the rest"
            ],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("denoise", "broadband", "learn-profile"),
        )
    ]
    if issue.severity is not Severity.MINOR:
        steps.append(
            ProcessingStep(
                role=StepRole.GATE,
                severity=Severity.MINOR,
                settings=[
                    "Expander rather than a hard gate: 6-10 dB of range, threshold under the "
                    "quietest word, 5 ms attack, 150 ms release, hold 50 ms so breaths do not "
                    "chatter"
                ],
                reasons=["Cleans the gaps that de-noising alone leaves audible."],
                issues=[issue.name],
                preferred_tags=("expander", "gate", "transparent"),
            )
        )
    return steps


def _mains_hum(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    freq = _evidence(issue, "hum_freq_hz", 50.0)
    harmonics = ", ".join(f"{freq * k:.0f} Hz" for k in (1, 2, 3))
    return [
        ProcessingStep(
            role=StepRole.NOISE_REDUCTION,
            severity=issue.severity,
            settings=[
                f"De-hum at {freq:.0f} Hz, or notch {harmonics} by hand at Q 20-30. Fix the "
                "cable or the ground loop before the next take — this is cheaper to prevent "
                "than to repair"
            ],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("hum", "repair", "surgical"),
        )
    ]


def _room_reflections(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    tail = _evidence(issue, "rt60_ms", profile.room_quality.reverb_tail_ms)
    return [
        ProcessingStep(
            role=StepRole.NOISE_REDUCTION,
            severity=issue.severity,
            settings=[
                f"De-reverb by 20-30% — enough to shorten the {tail / 1000:.1f} s tail, not enough "
                "to make the vocal sound like it was recorded in a vacuum. Artifacts here are "
                "worse than the room"
            ],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("dereverb", "room"),
        )
    ]


def _pitch_drift(issue: VocalIssue, profile: VocalProfile) -> list[ProcessingStep]:
    drift = _evidence(issue, "drift_cents", profile.pitch_stability.drift_cents)
    hard = issue.severity is Severity.CRITICAL
    return [
        ProcessingStep(
            role=StepRole.PITCH,
            severity=issue.severity,
            settings=[
                f"Set the scale to the song's key and correct the roughly {drift:.0f} cents of "
                + (
                    "wander with a fast retune (speed 10-20) — at this much drift, gentle "
                    "correction will not catch it"
                    if hard
                    else "wander with a slow retune (speed 25-40) so the vibrato survives"
                )
            ],
            reasons=[issue.description],
            issues=[issue.name],
            preferred_tags=("tuning", "formant", "transparent"),
        )
    ]


_ISSUE_BUILDERS = {
    "Low-Mid Buildup": _low_mid_buildup,
    "Boxiness": _boxiness,
    "Thin Body": _thin_body,
    "Harsh Presence": _harsh_presence,
    "Lacks Presence": _lacks_presence,
    "Lacks Air": _lacks_air,
    "Sibilance": _sibilance,
    "Uneven Dynamics": _uneven_dynamics,
    "Audible Noise Floor": _noise_floor,
    "Mains Hum": _mains_hum,
    "Room Reflections": _room_reflections,
    "Pitch Drift": _pitch_drift,
}


# --- steps every chain gets ------------------------------------------------


def _baseline_steps(
    profile: VocalProfile, existing: dict[StepRole, ProcessingStep]
) -> list[ProcessingStep]:
    """Compression, space and peak control, so a chain is coherent on a clean take too."""
    steps: list[ProcessingStep] = []

    if StepRole.COMPRESSION not in existing:
        steps.append(
            ProcessingStep(
                role=StepRole.COMPRESSION,
                settings=[
                    "Ratio 2:1, attack 10 ms, release 100 ms, threshold for 2-3 dB of gain "
                    "reduction on the loudest words — the take is already even, so this is "
                    "for glue, not control"
                ],
                reasons=["Every vocal wants some hand on the fader."],
                preferred_tags=("glue", "transparent", "leveling"),
            )
        )

    steps.append(_spatial_step(profile))

    crest = profile.dynamic_range.crest_factor_db
    if crest > 20.0 and StepRole.LIMITER not in existing:
        steps.append(
            ProcessingStep(
                role=StepRole.LIMITER,
                settings=[
                    f"Ceiling at -1 dBFS, catching the last 2-3 dB of stray peaks "
                    f"(crest factor is {crest:.0f} dB). It is a safety net, not a level control"
                ],
                reasons=["Isolated peaks are still well above the body of the performance."],
                preferred_tags=("brickwall", "transparent"),
            )
        )
    return steps


def _spatial_step(profile: VocalProfile) -> ProcessingStep:
    room = profile.room_quality
    if not room.treated:
        settings = (
            f"Short plate or small room, 0.8-1.2 s, 8-12% wet, pre-delay 30-40 ms, high-pass "
            f"the return at 300 Hz. Keep it small: the take already carries a room that "
            f"takes {room.reverb_tail_ms / 1000:.1f} s to die away, and stacking a second space on "
            "that is what makes bedroom vocals sound distant"
        )
        reason = "The recording has audible room on it already, so added space has to be modest."
        tags = ("plate", "short", "transparent")
    else:
        settings = (
            "Plate at 1.2-1.6 s, 15-20% wet, pre-delay 25-40 ms so the words stay dry and the "
            "tail sits behind them, high-pass the return at 250 Hz"
        )
        reason = "A dry take needs a space of its own to sit in the track."
        tags = ("plate", "character", "room")

    return ProcessingStep(
        role=StepRole.SPATIAL,
        settings=[settings],
        reasons=[reason],
        preferred_tags=tags,
    )
