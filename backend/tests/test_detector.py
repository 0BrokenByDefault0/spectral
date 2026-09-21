"""Dry vocal vs full mix classification."""

from __future__ import annotations

import numpy as np

from app.analysis import detector
from app.models.schemas import SourceType
from tests import synth


def test_dry_vocal_is_recognised():
    result = detector.detect_samples(synth.vocal(), synth.SR)
    assert result.source_type is SourceType.DRY_VOCAL
    assert result.confidence >= 0.75
    assert result.sub_bass_ratio < detector.SUB_BASS_MIX


def test_full_mix_is_recognised():
    result = detector.detect_samples(synth.full_mix(), synth.SR)
    assert result.source_type is SourceType.FULL_MIX
    assert result.confidence >= 0.75
    assert result.reasons


def test_noisy_vocal_is_still_a_vocal():
    noisy = synth.with_noise(synth.vocal(), snr_db=15.0)
    assert detector.detect_samples(noisy, synth.SR).source_type is SourceType.DRY_VOCAL


def test_reasons_describe_the_verdict():
    result = detector.detect_samples(synth.full_mix(), synth.SR)
    assert any("onsets/s" in reason or "percussive" in reason for reason in result.reasons)


def test_silence_does_not_crash():
    result = detector.detect_samples(np.zeros(2 * synth.SR, dtype=np.float32), synth.SR)
    assert result.source_type is SourceType.DRY_VOCAL
