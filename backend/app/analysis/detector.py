"""Heuristic classifier: is this upload a dry vocal or a full mix?

A full mix almost always carries three things a solo vocal does not: real energy
below 100 Hz, a strong percussive component after harmonic/percussive separation,
and a steady stream of transients. Each is scored independently and the votes are
combined so that no single measurement can flip the verdict on its own.
"""

from __future__ import annotations

import numpy as np
import librosa

from app.analysis.spectral import HOP_LENGTH, N_FFT, SAMPLE_RATE, load_audio
from app.models.schemas import SourceDetection, SourceType

#: Share of total energy below 100 Hz. A dry vocal rarely clears a couple of percent.
SUB_BASS_HZ = 100.0
SUB_BASS_MIX = 0.05

#: Share of energy that survives as "percussive" after HPSS.
PERCUSSIVE_MIX = 0.10

#: Detected onsets per second. Drums push this past a syllable rate.
ONSET_RATE_MIX = 4.0

#: Vote weights, and the score out of 4 at which the verdict flips to full mix.
SUB_BASS_WEIGHT = 2
MIX_SCORE = 3
_MAX_SCORE = SUB_BASS_WEIGHT + 2

_EPS = 1e-12


def detect(path: str, sample_rate: int = SAMPLE_RATE) -> SourceDetection:
    """Classify an audio file as a dry vocal or a full mix."""
    y, sr = load_audio(path, sample_rate)
    return detect_samples(y, sr)


def detect_samples(y: np.ndarray, sr: int) -> SourceDetection:
    """Same as `detect`, for samples already in memory."""
    sub_bass = _sub_bass_ratio(y, sr)
    percussive = _percussive_ratio(y)
    onset_rate = _onset_rate(y, sr)

    # Sub-bass energy is the strongest single signal, so it carries two votes: on its
    # own it is not enough, but with either corroborating measurement it decides.
    votes = [
        (
            sub_bass > SUB_BASS_MIX,
            SUB_BASS_WEIGHT,
            f"{sub_bass:.1%} of energy below {SUB_BASS_HZ:.0f} Hz",
        ),
        (percussive > PERCUSSIVE_MIX, 1, f"{percussive:.1%} percussive energy after HPSS"),
        (onset_rate > ONSET_RATE_MIX, 1, f"{onset_rate:.1f} onsets/s"),
    ]
    score = sum(weight for is_mix_vote, weight, _ in votes if is_mix_vote)
    is_mix = score >= MIX_SCORE

    reasons = [reason for is_mix_vote, _, reason in votes if is_mix_vote == is_mix]
    confidence = (score if is_mix else _MAX_SCORE - score) / _MAX_SCORE

    return SourceDetection(
        source_type=SourceType.FULL_MIX if is_mix else SourceType.DRY_VOCAL,
        confidence=float(confidence),
        sub_bass_ratio=float(sub_bass),
        percussive_ratio=float(percussive),
        onset_rate_hz=float(onset_rate),
        reasons=reasons,
    )


def _sub_bass_ratio(y: np.ndarray, sr: int) -> float:
    spec = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    low = (freqs >= 20.0) & (freqs < SUB_BASS_HZ)
    total = spec.sum() + _EPS
    return float(spec[low].sum() / total)


def _percussive_ratio(y: np.ndarray) -> float:
    harmonic, percussive = librosa.effects.hpss(y)
    h_energy = float(np.sum(harmonic**2))
    p_energy = float(np.sum(percussive**2))
    return p_energy / (h_energy + p_energy + _EPS)


def _onset_rate(y: np.ndarray, sr: int) -> float:
    onsets = librosa.onset.onset_detect(y=y, sr=sr, hop_length=HOP_LENGTH, units="time")
    duration = y.size / sr
    return float(len(onsets) / duration) if duration > 0 else 0.0
