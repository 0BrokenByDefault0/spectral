"""Synthetic vocal-ish signals, so the analysis has something deterministic to chew on.

These are not vocals — they are signals with the properties the analysis looks for, which
is what the unit tests need. Real recordings are what the Phase 1 validation gate is for.
"""

from __future__ import annotations

import numpy as np

SR = 44100


def _rng(seed: int) -> np.random.Generator:
    """Per-helper generator: results must not depend on what ran before."""
    return np.random.default_rng(seed)


def _phrase_envelope(n: int, sr: int, note_s: float = 0.45, gap_s: float = 0.2) -> np.ndarray:
    """Sung phrases separated by near-silence, with a short decay after each note."""
    env = np.zeros(n)
    note, gap = int(note_s * sr), int(gap_s * sr)
    attack = int(0.02 * sr)
    pos = 0
    while pos + note < n:
        shape = np.ones(note)
        shape[:attack] = np.linspace(0.0, 1.0, attack)
        shape[-attack:] = np.linspace(1.0, 0.0, attack)
        env[pos : pos + note] = shape
        pos += note + gap
    return env


def vocal(
    duration_s: float = 6.0,
    sr: int = SR,
    f0: float = 180.0,
    tilt: float = 0.8,
    breath: float = 0.02,
    vibrato_cents: float = 20.0,
    drift_cents: float = 0.0,
) -> np.ndarray:
    """A harmonic tone with vibrato, phrase envelope and a roughly vocal spectral tilt.

    `tilt` and `breath` are set so the result lands close to the reference balance in
    `spectral.REFERENCE_BALANCE` — it stands in for a decent, unprocessed take.
    """
    n = int(duration_s * sr)
    t = np.arange(n) / sr

    vibrato = vibrato_cents * np.sin(2 * np.pi * 5.5 * t)
    drift = drift_cents * np.sin(2 * np.pi * 0.35 * t) if drift_cents else 0.0
    freq = f0 * 2 ** ((vibrato + drift) / 1200.0)
    phase = 2 * np.pi * np.cumsum(freq) / sr

    signal = np.zeros(n)
    for k in range(1, int(sr / 2 / f0) + 1):
        signal += _formant_gain(f0 * k) * np.sin(k * phase) / k**tilt

    # Real voices carry broadband breath noise on top of the harmonic series, which is
    # most of what lands in the presence and air bands.
    signal = signal / np.max(np.abs(signal)) + breath * _bandlimited_noise(n, sr, 1500.0, 16000.0)
    signal *= _phrase_envelope(n, sr)
    return _normalize(signal, 0.5)


#: Rough vowel formants (centre Hz, width Hz, gain) — enough to shape the harmonic series.
_FORMANTS = ((500.0, 300.0, 2.0), (1500.0, 500.0, 1.0), (2800.0, 800.0, 0.7))


def _formant_gain(freq: float) -> float:
    return 1.0 + sum(g * np.exp(-(((freq - c) / w) ** 2)) for c, w, g in _FORMANTS)


def with_band_boost(y: np.ndarray, low: float, high: float, gain_db: float, sr: int = SR) -> np.ndarray:
    """Boost (or cut) a band by filtering in the frequency domain."""
    spectrum = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(y.size, d=1.0 / sr)
    band = (freqs >= low) & (freqs < high)
    spectrum[band] *= 10 ** (gain_db / 20.0)
    return _normalize(np.fft.irfft(spectrum, n=y.size), 0.5)


def with_sibilance(y: np.ndarray, sr: int = SR, level: float = 0.5) -> np.ndarray:
    """Add filtered noise bursts where the phrases start, like hard esses."""
    noise = _bandlimited_noise(y.size, sr, 5000.0, 9500.0)
    bursts = np.zeros(y.size)
    step = int(0.65 * sr)
    burst = int(0.07 * sr)
    for start in range(0, y.size - burst, step):
        bursts[start : start + burst] = np.hanning(burst)
    return _normalize(y + level * noise * bursts, 0.5)


def with_noise(y: np.ndarray, snr_db: float, sr: int = SR, seed: int = 11) -> np.ndarray:
    """Add broadband noise at a target SNR relative to the loud passages."""
    active = np.abs(y) > 0.05 * np.max(np.abs(y))
    signal_rms = float(np.sqrt(np.mean(y[active] ** 2))) if active.any() else 0.1
    noise = _rng(seed).normal(0.0, 1.0, y.size)
    noise *= (signal_rms / 10 ** (snr_db / 20.0)) / float(np.sqrt(np.mean(noise**2)))
    return y + noise


def with_hum(y: np.ndarray, freq: float = 60.0, level: float = 0.02, sr: int = SR) -> np.ndarray:
    """Add a mains tone plus its first two harmonics."""
    t = np.arange(y.size) / sr
    hum = sum(level / k * np.sin(2 * np.pi * freq * k * t) for k in (1, 2, 3))
    return y + hum


def with_reverb(
    y: np.ndarray, tail_s: float = 0.8, sr: int = SR, wet: float = 0.4, seed: int = 22
) -> np.ndarray:
    """Convolve with an exponentially decaying noise tail."""
    n = int(tail_s * sr)
    impulse = _rng(seed).normal(0.0, 1.0, n) * np.exp(-np.arange(n) / (n / 5.0))
    impulse[0] = 1.0
    wet_signal = np.convolve(y, impulse, mode="full")[: y.size]
    return _normalize(y + wet * _normalize(wet_signal, 1.0), 0.5)


def with_dynamics(y: np.ndarray, spread_db: float = 20.0, sr: int = SR) -> np.ndarray:
    """Swing the level slowly so loud and quiet passages differ by `spread_db`."""
    t = np.arange(y.size) / sr
    swing = 10 ** (-spread_db / 2 / 20.0 * (1 + np.sin(2 * np.pi * 0.28 * t)))
    return _normalize(y * swing, 0.5)


def full_mix(duration_s: float = 6.0, sr: int = SR, seed: int = 33) -> np.ndarray:
    """Vocal over kick, snare, hats and a bass line — a crude but honest full mix."""
    n = int(duration_s * sr)
    t = np.arange(n) / sr
    y = vocal(duration_s, sr)

    rng = _rng(seed)
    beat = int(0.5 * sr)
    drums = np.zeros(n)
    hit = int(0.18 * sr)
    body = np.exp(-np.arange(hit) / (0.05 * sr))
    click = np.exp(-np.arange(hit) / (0.002 * sr))

    for i, start in enumerate(range(0, n - hit, beat)):
        end = start + hit
        if i % 2 == 0:  # kick: a low thump with a transient on the front
            thump = np.sin(2 * np.pi * 55 * np.arange(hit) / sr) * body
            drums[start:end] += 0.9 * thump + 0.5 * rng.normal(0.0, 1.0, hit) * click
        else:  # snare
            drums[start:end] += 0.5 * rng.normal(0.0, 1.0, hit) * body

    hat = int(0.05 * sr)
    hat_decay = np.exp(-np.arange(hat) / (0.008 * sr))
    for start in range(0, n - hat, beat // 4):  # eighth-note hats
        drums[start : start + hat] += 0.25 * _bandlimited_noise(hat, sr, 6000.0, 14000.0) * hat_decay

    bass = 0.4 * np.sin(2 * np.pi * 82.0 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 1.0 * t))
    return _normalize(0.6 * y + drums + bass, 0.7)


def _bandlimited_noise(n: int, sr: int, low: float, high: float, seed: int = 44) -> np.ndarray:
    spectrum = np.fft.rfft(_rng(seed).normal(0.0, 1.0, n))
    freqs = np.fft.rfftfreq(n, d=1.0 / sr)
    spectrum[(freqs < low) | (freqs > high)] = 0.0
    return _normalize(np.fft.irfft(spectrum, n=n), 1.0)


def _normalize(y: np.ndarray, peak: float) -> np.ndarray:
    largest = float(np.max(np.abs(y)))
    return (y * (peak / largest)).astype(np.float32) if largest > 0 else y.astype(np.float32)
