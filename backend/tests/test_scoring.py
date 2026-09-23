"""The radar scores: presentation numbers, derived from the same measurements."""

from __future__ import annotations

import pytest

from app.analysis import scoring, spectral
from tests import synth


def features(signal):
    return spectral.analyze_samples(signal, synth.SR)


@pytest.fixture(scope="module")
def clean():
    return scoring.score(features(synth.vocal()))


def test_every_axis_is_scored(clean):
    assert set(clean) == set(scoring.AXES)
    assert all(0.0 <= value <= 100.0 for value in clean.values())


def test_a_clean_take_scores_well(clean):
    """Nothing on a clean take should read as a problem.

    Tonal balance is the loosest of these on purpose: it is measured against
    `REFERENCE_BALANCE`, which is still a provisional constant, so its absolute value
    will move when that is calibrated. The axes that depend on nothing but the signal
    itself are held much tighter.
    """
    assert all(value >= 60.0 for value in clean.values()), clean
    for axis in ("noise", "room", "dynamics"):
        assert clean[axis] >= 90.0, clean


def test_noise_lowers_the_noise_axis(clean):
    noisy = scoring.score(features(synth.with_noise(synth.vocal(), snr_db=18.0)))
    assert noisy["noise"] < clean["noise"]


def test_hum_caps_the_noise_axis():
    hummed = scoring.score(features(synth.with_hum(synth.vocal(), freq=60.0)))
    assert hummed["noise"] <= 50.0


def test_a_live_room_lowers_the_room_axis(clean):
    wet = scoring.score(features(synth.with_reverb(synth.vocal(), tail_s=1.2, wet=0.7)))
    assert wet["room"] < clean["room"]


def test_sibilance_lowers_the_sibilance_axis(clean):
    sibilant = scoring.score(features(synth.with_sibilance(synth.vocal())))
    assert sibilant["sibilance"] < clean["sibilance"]


def test_level_swings_lower_the_dynamics_axis(clean):
    swung = scoring.score(features(synth.with_dynamics(synth.vocal(), spread_db=24.0)))
    assert swung["dynamics"] < clean["dynamics"]


def test_mud_lowers_clarity_and_balance(clean):
    muddy = scoring.score(features(synth.with_band_boost(synth.vocal(), 200.0, 500.0, 12.0)))
    assert muddy["clarity"] < clean["clarity"]
    assert muddy["tonal_balance"] < clean["tonal_balance"]


def test_unscored_bands_are_left_out_of_balance():
    """A band the source does not have must not drag the balance score down.

    The scores are not expected to match: dropping the unscored bands drops whatever
    they deviated by, so a band-limited take can score higher. What must never happen is
    the reverse — being penalised for bands it was never judged on.
    """
    limited = scoring.score(features(synth.with_lowpass(synth.vocal(), 8000.0)))
    full = scoring.score(features(synth.vocal()))
    assert limited["tonal_balance"] >= full["tonal_balance"] - 1.0


def test_scores_reach_the_profile():
    from app.analysis import merger
    from tests.test_merger import SOURCE

    profile = merger.merge(features(synth.vocal()), None, SOURCE)
    assert set(profile.scores) == set(scoring.AXES)
