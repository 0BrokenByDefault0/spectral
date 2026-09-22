"""The plan the engine produces, and the chains built from it."""

from __future__ import annotations

import pytest

from app.db import seed
from app.db.repository import PluginCatalog
from app.models.schemas import (
    BandScore,
    DynamicRange,
    NoiseFloor,
    PitchStability,
    ProcessingCategory,
    RoomQuality,
    Severity,
    SibilanceProfile,
    SourceDetection,
    SourceType,
    Tier,
    VocalIssue,
    VocalProfile,
)
from app.recommendation import engine
from app.recommendation.chain_builder import CHAIN_ORDER, build_chains, order_steps
from app.recommendation.engine import StepRole, plan


@pytest.fixture(scope="module")
def catalog():
    return PluginCatalog(seed.load_catalog())


def band(name, deviation, severity=Severity.MODERATE):
    return BandScore(
        band_name=name,
        low_hz=200.0,
        high_hz=500.0,
        energy=0.3,
        deviation_db=deviation,
        severity=severity,
    )


def profile_with(*issues, treated=True, crest=12.0, snr=50.0, tail=50.0, drift=5.0):
    """A profile carrying exactly the issues a test cares about."""
    return VocalProfile(
        source=SourceDetection(
            source_type=SourceType.DRY_VOCAL,
            confidence=1.0,
            sub_bass_ratio=0.0,
            percussive_ratio=0.0,
            onset_rate_hz=1.0,
        ),
        frequency_bands={"low_mid": band("low_mid", 0.0, Severity.MINOR)},
        dynamic_range=DynamicRange(
            crest_factor_db=crest,
            rms_db=-18.0,
            peak_db=-6.0,
            loud_quiet_spread_db=8.0,
            needs_compression=False,
        ),
        noise_floor=NoiseFloor(
            snr_db=snr, noise_floor_db=-70.0, has_hum=False, has_broadband=False
        ),
        room_quality=RoomQuality(reverb_tail_ms=tail, treated=treated, reflection_level=0.1),
        pitch_stability=PitchStability(
            drift_cents=drift, vibrato_consistency=0.5, voiced_ratio=0.8, needs_correction=False
        ),
        sibilance=SibilanceProfile(ratio=0.01, peak_freq_hz=6000.0, severity=Severity.MINOR),
        issues=list(issues),
        qualitative_summary="",
    )


def issue(name, category, severity=Severity.MODERATE, evidence=None, confidence=0.7):
    return VocalIssue(
        name=name,
        category=category,
        severity=severity,
        confidence=confidence,
        description=f"{name} description.",
        spectral_evidence=evidence,
    )


def roles(steps):
    return [step.role for step in steps]


def step_for(steps, role):
    return next(step for step in steps if step.role is role)


# --- the plan --------------------------------------------------------------


def test_a_clean_take_still_gets_a_coherent_chain():
    steps = plan(profile_with())
    assert roles(steps) == [StepRole.COMPRESSION, StepRole.SPATIAL] or set(roles(steps)) == {
        StepRole.COMPRESSION,
        StepRole.SPATIAL,
    }
    assert "glue" in step_for(steps, StepRole.COMPRESSION).settings_text()


def test_settings_are_derived_from_the_measurement():
    steps = plan(
        profile_with(
            issue(
                "Low-Mid Buildup",
                ProcessingCategory.EQ,
                evidence={"deviation_db": 4.5, "band": "low_mid"},
            )
        )
    )
    settings = step_for(steps, StepRole.SUBTRACTIVE_EQ).settings_text()
    assert "-4.5 dB" in settings
    assert "High-pass at 80 Hz" in settings


def test_a_cut_never_exceeds_six_db_in_one_bell():
    steps = plan(
        profile_with(
            issue("Low-Mid Buildup", ProcessingCategory.EQ, evidence={"deviation_db": 22.0})
        )
    )
    assert "-6.0 dB" in step_for(steps, StepRole.SUBTRACTIVE_EQ).settings_text()


def test_cuts_and_boosts_land_in_separate_steps():
    steps = plan(
        profile_with(
            issue("Low-Mid Buildup", ProcessingCategory.EQ, evidence={"deviation_db": 4.0}),
            issue("Lacks Air", ProcessingCategory.EQ, evidence={"deviation_db": -4.0}),
        )
    )
    assert "-4.0 dB" in step_for(steps, StepRole.SUBTRACTIVE_EQ).settings_text()
    assert "+4.0 dB" in step_for(steps, StepRole.ADDITIVE_EQ).settings_text()


def test_two_cuts_merge_into_one_eq_step():
    steps = plan(
        profile_with(
            issue("Low-Mid Buildup", ProcessingCategory.EQ, evidence={"deviation_db": 4.0}),
            issue("Boxiness", ProcessingCategory.EQ, evidence={"deviation_db": 3.5}),
        )
    )
    eq = step_for(steps, StepRole.SUBTRACTIVE_EQ)
    assert eq.issues == ["Low-Mid Buildup", "Boxiness"]
    assert "200-500 Hz" in eq.settings_text()
    assert "900 Hz-1 kHz" in eq.settings_text()
    assert len([r for r in roles(steps) if r is StepRole.SUBTRACTIVE_EQ]) == 1


def test_the_worst_severity_wins_a_merged_step():
    steps = plan(
        profile_with(
            issue("Low-Mid Buildup", ProcessingCategory.EQ, Severity.MINOR, {"deviation_db": 3.0}),
            issue("Boxiness", ProcessingCategory.EQ, Severity.CRITICAL, {"deviation_db": 8.0}),
        )
    )
    assert step_for(steps, StepRole.SUBTRACTIVE_EQ).severity is Severity.CRITICAL


def test_noise_brings_a_gate_with_it():
    steps = plan(
        profile_with(
            issue(
                "Audible Noise Floor",
                ProcessingCategory.NOISE_REDUCTION,
                Severity.MODERATE,
                {"snr_db": 22.0},
            )
        )
    )
    assert StepRole.GATE in roles(steps)
    assert "10 dB" in step_for(steps, StepRole.NOISE_REDUCTION).settings_text()


def test_mild_noise_does_not_bring_a_gate():
    steps = plan(
        profile_with(
            issue(
                "Audible Noise Floor",
                ProcessingCategory.NOISE_REDUCTION,
                Severity.MINOR,
                {"snr_db": 37.0},
            )
        )
    )
    assert StepRole.GATE not in roles(steps)


def test_hum_settings_name_the_harmonics():
    steps = plan(
        profile_with(
            issue("Mains Hum", ProcessingCategory.NOISE_REDUCTION, evidence={"hum_freq_hz": 60.0})
        )
    )
    settings = step_for(steps, StepRole.NOISE_REDUCTION).settings_text()
    assert "60 Hz" in settings and "120 Hz" in settings and "180 Hz" in settings


def test_a_thin_take_gets_saturation_as_well_as_eq():
    steps = plan(
        profile_with(issue("Thin Body", ProcessingCategory.EQ, evidence={"deviation_db": -4.0}))
    )
    assert StepRole.ADDITIVE_EQ in roles(steps)
    assert StepRole.SATURATION in roles(steps)


def test_air_advice_warns_when_the_noise_floor_is_high():
    noisy = plan(
        profile_with(
            issue("Lacks Air", ProcessingCategory.EQ, evidence={"deviation_db": -4.0}), snr=28.0
        )
    )
    assert "hiss" in step_for(noisy, StepRole.ADDITIVE_EQ).settings_text()

    quiet = plan(
        profile_with(
            issue("Lacks Air", ProcessingCategory.EQ, evidence={"deviation_db": -4.0}), snr=55.0
        )
    )
    assert "hiss" not in step_for(quiet, StepRole.ADDITIVE_EQ).settings_text()


def test_a_wide_dynamic_swing_suggests_two_stages():
    steps = plan(
        profile_with(
            issue(
                "Uneven Dynamics",
                ProcessingCategory.COMPRESSION,
                Severity.CRITICAL,
                {"loud_quiet_spread_db": 24.0},
            )
        )
    )
    compression = step_for(steps, StepRole.COMPRESSION)
    assert "4:1" in compression.settings_text()
    assert "two gentle stages" in compression.settings_text()


def test_space_advice_depends_on_the_room():
    live = step_for(plan(profile_with(treated=False, tail=400.0)), StepRole.SPATIAL)
    assert "Keep it small" in live.settings_text()
    assert "400 ms" in live.settings_text()

    dry = step_for(plan(profile_with(treated=True)), StepRole.SPATIAL)
    assert "Keep it small" not in dry.settings_text()


def test_a_high_crest_factor_adds_peak_control():
    assert StepRole.LIMITER in roles(plan(profile_with(crest=24.0)))
    assert StepRole.LIMITER not in roles(plan(profile_with(crest=12.0)))


def test_pitch_advice_follows_the_amount_of_drift():
    gentle = step_for(
        plan(
            profile_with(
                issue(
                    "Pitch Drift",
                    ProcessingCategory.PITCH_CORRECTION,
                    Severity.MODERATE,
                    {"drift_cents": 30.0},
                )
            )
        ),
        StepRole.PITCH,
    )
    assert "slow retune" in gentle.settings_text()

    hard = step_for(
        plan(
            profile_with(
                issue(
                    "Pitch Drift",
                    ProcessingCategory.PITCH_CORRECTION,
                    Severity.CRITICAL,
                    {"drift_cents": 80.0},
                )
            )
        ),
        StepRole.PITCH,
    )
    assert "fast retune" in hard.settings_text()


def test_an_issue_only_the_llm_raised_still_gets_a_step():
    steps = plan(
        profile_with(
            issue("Mouth clicks", ProcessingCategory.NOISE_REDUCTION, confidence=0.55)
        )
    )
    settings = step_for(steps, StepRole.NOISE_REDUCTION).settings_text()
    assert "Set by ear" in settings


def test_a_delay_issue_lands_in_the_spatial_step():
    steps = plan(profile_with(issue("Needs a throw", ProcessingCategory.DELAY)))
    assert StepRole.SPATIAL in roles(steps)


# --- ordering and chains ---------------------------------------------------


def test_steps_come_out_in_signal_order():
    steps = plan(
        profile_with(
            issue("Audible Noise Floor", ProcessingCategory.NOISE_REDUCTION, evidence={"snr_db": 20.0}),
            issue("Low-Mid Buildup", ProcessingCategory.EQ, evidence={"deviation_db": 4.0}),
            issue("Lacks Air", ProcessingCategory.EQ, evidence={"deviation_db": -4.0}),
            issue("Sibilance", ProcessingCategory.DE_ESS, evidence={"peak_freq_hz": 7000.0}),
            issue("Pitch Drift", ProcessingCategory.PITCH_CORRECTION, evidence={"drift_cents": 40.0}),
        )
    )
    ordered = roles(order_steps(steps))
    assert ordered == [role for role in CHAIN_ORDER if role in ordered]


def test_critical_sibilance_moves_the_de_esser_before_the_compressor():
    steps = plan(
        profile_with(
            issue(
                "Sibilance",
                ProcessingCategory.DE_ESS,
                Severity.CRITICAL,
                {"peak_freq_hz": 7000.0},
            ),
            issue("Uneven Dynamics", ProcessingCategory.COMPRESSION, evidence={"loud_quiet_spread_db": 14.0}),
        )
    )
    ordered = roles(order_steps(steps))
    assert ordered.index(StepRole.DE_ESS) < ordered.index(StepRole.COMPRESSION)


def test_moderate_sibilance_stays_after_the_compressor():
    steps = plan(
        profile_with(
            issue("Sibilance", ProcessingCategory.DE_ESS, Severity.MODERATE, {"peak_freq_hz": 7000.0}),
            issue("Uneven Dynamics", ProcessingCategory.COMPRESSION, evidence={"loud_quiet_spread_db": 14.0}),
        )
    )
    ordered = roles(order_steps(steps))
    assert ordered.index(StepRole.DE_ESS) > ordered.index(StepRole.COMPRESSION)


def test_three_chains_are_built_from_one_plan(catalog):
    chains = build_chains(profile_with(issue("Sibilance", ProcessingCategory.DE_ESS)), catalog)
    assert [chain.tier for chain in chains] == [Tier.FREE, Tier.MID, Tier.PREMIUM]
    assert all(chain.steps for chain in chains)
    # Same plan, so the same processing in the same order at every price point.
    shapes = {tuple(step.category for step in chain.steps) for chain in chains}
    assert len(shapes) == 1


def test_the_free_chain_is_actually_free(catalog):
    free = build_chains(profile_with(), catalog, tiers=(Tier.FREE,))[0]
    assert all(step.tier is Tier.FREE for step in free.steps)
    assert all("Free" in step.price for step in free.steps)


def test_every_recommendation_explains_itself(catalog):
    chains = build_chains(
        profile_with(issue("Low-Mid Buildup", ProcessingCategory.EQ, evidence={"deviation_db": 4.0})),
        catalog,
    )
    for chain in chains:
        for step in chain.steps:
            assert step.suggested_settings.strip()
            assert step.why.strip()
            assert step.purchase_url


def test_a_boost_slot_never_gets_a_cut_only_plugin(catalog):
    chains = build_chains(
        profile_with(issue("Lacks Presence", ProcessingCategory.EQ, evidence={"deviation_db": -5.0})),
        catalog,
    )
    cut_only = {
        e.name for e in catalog.entries if "cut-only" in e.tags
    }
    for chain in chains:
        tone_steps = [
            step
            for step in chain.steps
            if step.suggested_settings.startswith(engine.ROLE_LABELS[StepRole.ADDITIVE_EQ])
        ]
        assert tone_steps
        assert not any(step.plugin_name in cut_only for step in tone_steps)


def test_a_repeated_eq_is_labelled_as_a_second_instance(catalog):
    chain = build_chains(
        profile_with(
            issue("Low-Mid Buildup", ProcessingCategory.EQ, evidence={"deviation_db": 4.0}),
            issue("Lacks Presence", ProcessingCategory.EQ, evidence={"deviation_db": -4.0}),
        ),
        catalog,
        tiers=(Tier.PREMIUM,),
    )[0]
    names = [step.plugin_name for step in chain.steps]
    repeated = [name for name in names if names.count(name) > 1]
    assert repeated, "the premium EQ should be reused rather than swapped for a worse one"
    second = [step for step in chain.steps if step.plugin_name in repeated][1]
    assert "second instance" in second.why


def test_distinct_roles_do_not_repeat_a_plugin_needlessly(catalog):
    chain = build_chains(
        profile_with(
            issue("Audible Noise Floor", ProcessingCategory.NOISE_REDUCTION, evidence={"snr_db": 20.0}),
            issue("Room Reflections", ProcessingCategory.NOISE_REDUCTION, evidence={"reverb_tail_ms": 500.0}),
        ),
        catalog,
        tiers=(Tier.MID,),
    )[0]
    gates = [step for step in chain.steps if step.category is ProcessingCategory.GATE]
    cleanup = [step for step in chain.steps if step.category is ProcessingCategory.NOISE_REDUCTION]
    assert gates and cleanup
    assert gates[0].plugin_name != cleanup[0].plugin_name


def test_a_tier_substitution_is_disclosed():
    sparse = PluginCatalog(
        [
            e
            for e in seed.load_catalog()
            if not (e.category is ProcessingCategory.REVERB and e.tier is Tier.FREE)
        ]
    )
    chain = build_chains(profile_with(), sparse, tiers=(Tier.FREE,))[0]
    spatial = [step for step in chain.steps if step.category is ProcessingCategory.REVERB][0]
    assert spatial.tier is not Tier.FREE
    assert "at the free tier" in spatial.why


def test_chains_survive_a_category_missing_entirely():
    without_reverb = PluginCatalog(
        [e for e in seed.load_catalog() if e.category is not ProcessingCategory.REVERB]
    )
    chain = build_chains(profile_with(), without_reverb, tiers=(Tier.FREE,))[0]
    assert chain.steps
    assert all(step.category is not ProcessingCategory.REVERB for step in chain.steps)
