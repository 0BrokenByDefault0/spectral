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
    # Good takes measure a 22.7 dB spread, so an uneven one has to be worse than that.
    swung = spectral.analyze_samples(synth.with_dynamics(clean, spread_db=30.0), synth.SR)
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


def test_melody_is_not_drift():
    """Moving between notes is singing, not a tuning problem."""
    steady = spectral.analyze_samples(synth.melody(), synth.SR)
    assert steady.pitch_stability.drift_cents < 10.0
    assert not steady.pitch_stability.needs_correction


def test_wide_intervals_are_not_drift():
    octaves = spectral.analyze_samples(synth.melody(semitones=(0, 7, 12, 7, 0)), synth.SR)
    assert octaves.pitch_stability.drift_cents < 10.0


def test_legato_notes_are_split_on_pitch_not_silence():
    """With no gaps between notes, only pitch segmentation can separate them."""
    legato = spectral.analyze_samples(synth.legato_melody(), synth.SR)
    assert legato.pitch_stability.voiced_ratio > 0.9
    assert legato.pitch_stability.drift_cents < 10.0


def test_notes_that_slide_off_centre_are_drift():
    drifting = spectral.analyze_samples(
        synth.melody(per_note_drift_cents=140.0, vibrato_cents=0.0), synth.SR
    )
    assert drifting.pitch_stability.drift_cents > 15.0
    assert drifting.pitch_stability.needs_correction


def test_deep_vibrato_is_not_drift():
    wide = spectral.analyze_samples(synth.vocal(vibrato_cents=80.0), synth.SR)
    assert wide.pitch_stability.drift_cents < 10.0


def test_a_slow_vocal_release_is_not_a_room(clean):
    """A held note fading out decays like a room, and is not one."""
    released = spectral.analyze_samples(synth.with_slow_release(clean, 0.8), synth.SR)
    assert released.room_quality.treated
    assert released.room_quality.reverb_tail_ms < spectral.ROOM_TREATED_MS


def test_a_live_room_still_reads_as_live(clean):
    wet = spectral.analyze_samples(synth.with_reverb(clean, tail_s=1.2, wet=0.7), synth.SR)
    released = spectral.analyze_samples(synth.with_slow_release(clean, 0.8), synth.SR)
    assert wet.room_quality.reverb_tail_ms > released.room_quality.reverb_tail_ms * 3
    assert not wet.room_quality.treated


# --- RT60 against ground truth -------------------------------------------------

SCALE = (0, 2, 4, 5, 7, 9, 7, 5, 4, 2, 0, 4, 7, 4)


@pytest.fixture(scope="module")
def legato_scale():
    return synth.legato_melody(semitones=SCALE)


@pytest.mark.parametrize("rt60", [0.25, 0.5, 0.8, 1.2])
def test_rt60_tracks_a_known_room(legato_scale, rt60):
    """Measured from note transitions, the estimate lands near the true RT60."""
    room = spectral.analyze_samples(synth.with_room(legato_scale, rt60), synth.SR).room_quality
    assert room.measurement == "note transitions"
    assert room.probes >= spectral.MIN_TRANSITION_PROBES
    assert room.reverb_tail_ms / 1000.0 == pytest.approx(rt60, rel=0.35)


def test_rt60_orders_rooms_correctly(legato_scale):
    measured = [
        spectral.analyze_samples(synth.with_room(legato_scale, rt), synth.SR)
        .room_quality.reverb_tail_ms
        for rt in (0.3, 0.7, 1.2)
    ]
    assert measured == sorted(measured)


def test_a_dry_legato_take_offers_no_false_room(legato_scale):
    """No decay after a note change means no room — not a short one, none measured."""
    room = spectral.analyze_samples(legato_scale, synth.SR).room_quality
    assert room.treated
    assert room.reverb_tail_ms < spectral.ROOM_TREATED_MS


def test_the_room_threshold_is_crossed_where_acoustics_puts_it(legato_scale):
    booth = spectral.analyze_samples(synth.with_room(legato_scale, 0.2), synth.SR)
    bedroom = spectral.analyze_samples(synth.with_room(legato_scale, 0.7), synth.SR)
    assert booth.room_quality.treated
    assert not bedroom.room_quality.treated


def test_a_slow_release_in_a_dry_room_still_reads_dry():
    """The confound this measurement exists to beat: a long fade is not a room."""
    faded = synth.with_slow_release(synth.legato_melody(semitones=SCALE), 1.2)
    room = spectral.analyze_samples(faded, synth.SR).room_quality
    assert room.treated
