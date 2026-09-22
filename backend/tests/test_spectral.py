"""Spectral measurements move in the right direction when the signal changes."""

from __future__ import annotations

import numpy as np
import pytest

from app.analysis import spectral
from app.models.schemas import Severity
from tests import synth


@pytest.fixture(scope="module")
def clean():
    return synth.vocal()


@pytest.fixture(scope="module")
def clean_features(clean):
    return spectral.analyze_samples(clean, synth.SR)


def test_reports_every_band(clean_features):
    assert set(clean_features.frequency_bands) == set(spectral.BANDS)
    for band in clean_features.frequency_bands.values():
        assert 0.0 <= band.energy <= 1.0
        assert np.isfinite(band.deviation_db)


def test_low_mid_boost_raises_low_mid_deviation(clean, clean_features):
    muddy = spectral.analyze_samples(
        synth.with_band_boost(clean, 200.0, 500.0, 12.0), synth.SR
    )
    assert (
        muddy.frequency_bands["low_mid"].deviation_db
        > clean_features.frequency_bands["low_mid"].deviation_db + 2.0
    )


def test_high_cut_reads_as_lost_air(clean, clean_features):
    dark = spectral.analyze_samples(
        synth.with_band_boost(clean, 6000.0, 22000.0, -18.0), synth.SR
    )
    assert (
        dark.frequency_bands["air"].deviation_db
        < clean_features.frequency_bands["air"].deviation_db - 3.0
    )


def test_sibilance_bursts_are_detected(clean, clean_features):
    sibilant = spectral.analyze_samples(synth.with_sibilance(clean), synth.SR)
    assert sibilant.sibilance.ratio > clean_features.sibilance.ratio
    assert sibilant.sibilance.severity is not Severity.MINOR
    assert 4000.0 <= sibilant.sibilance.peak_freq_hz <= 11000.0


def test_added_noise_lowers_snr(clean, clean_features):
    noisy = spectral.analyze_samples(synth.with_noise(clean, snr_db=18.0), synth.SR)
    assert noisy.noise_floor.snr_db < clean_features.noise_floor.snr_db
    assert noisy.noise_floor.snr_db < 40.0
    assert noisy.noise_floor.has_broadband


def test_mains_hum_is_identified(clean):
    hummed = spectral.analyze_samples(synth.with_hum(clean, freq=60.0), synth.SR)
    assert hummed.noise_floor.has_hum
    assert hummed.noise_floor.hum_freq_hz == 60.0


def test_clean_take_has_no_hum(clean_features):
    assert not clean_features.noise_floor.has_hum


def test_reverb_lengthens_the_measured_tail(clean, clean_features):
    wet = spectral.analyze_samples(synth.with_reverb(clean, tail_s=1.2, wet=0.7), synth.SR)
    assert wet.room_quality.reverb_tail_ms > clean_features.room_quality.reverb_tail_ms
    assert not wet.room_quality.treated
    assert wet.room_quality.reflection_level > 0.0


def test_level_swings_flag_compression(clean, clean_features):
    swung = spectral.analyze_samples(synth.with_dynamics(clean, spread_db=24.0), synth.SR)
    assert swung.dynamic_range.loud_quiet_spread_db > (
        clean_features.dynamic_range.loud_quiet_spread_db
    )
    assert swung.dynamic_range.needs_compression


def test_pitch_tracking_finds_the_tone(clean_features):
    assert clean_features.pitch_stability.voiced_ratio > 0.3
    assert not clean_features.pitch_stability.needs_correction


def test_wandering_pitch_needs_correction(clean):
    drifting = spectral.analyze_samples(
        synth.vocal(drift_cents=120.0, vibrato_cents=0.0), synth.SR
    )
    stable = spectral.analyze_samples(clean, synth.SR)
    assert drifting.pitch_stability.drift_cents > stable.pitch_stability.drift_cents


def test_short_clips_are_rejected(tmp_path):
    import soundfile as sf

    path = tmp_path / "blip.wav"
    sf.write(path, np.zeros(int(0.4 * synth.SR), dtype=np.float32), synth.SR)
    with pytest.raises(spectral.AudioTooShortError):
        spectral.load_audio(str(path))


def test_silence_does_not_crash():
    silence = np.zeros(int(2.0 * synth.SR), dtype=np.float32)
    features = spectral.analyze_samples(silence, synth.SR)
    assert features.duration_s == pytest.approx(2.0, abs=0.01)
    assert np.isfinite(features.noise_floor.snr_db)


def test_full_band_audio_reports_no_cutoff(clean_features):
    assert clean_features.bandwidth_hz > spectral.BAND_LIMIT_HZ
    assert all(band.scored for band in clean_features.frequency_bands.values())


@pytest.mark.parametrize("cutoff", [8000.0, 11000.0])
def test_a_hard_cutoff_is_found(clean, cutoff):
    limited = spectral.analyze_samples(synth.with_lowpass(clean, cutoff), synth.SR)
    assert limited.bandwidth_hz == pytest.approx(cutoff, rel=0.15)


def test_bands_above_the_cutoff_are_not_scored(clean):
    limited = spectral.analyze_samples(synth.with_lowpass(clean, 8000.0), synth.SR)
    assert not limited.frequency_bands["ultra_high"].scored
    assert limited.frequency_bands["ultra_high"].deviation_db == 0.0
    assert limited.frequency_bands["low_mid"].scored
    assert limited.frequency_bands["presence"].scored


def test_a_gentle_rolloff_is_not_a_cutoff(clean):
    """A dull mic still has content up top; only a cliff means it is absent."""
    dark = spectral.analyze_samples(
        synth.with_band_boost(clean, 6000.0, 22000.0, -18.0), synth.SR
    )
    assert dark.bandwidth_hz > spectral.BAND_LIMIT_HZ
    assert dark.frequency_bands["air"].scored
