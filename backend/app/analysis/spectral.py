"""librosa-based spectral feature extraction.

Everything here is measurement only: it reports what the signal contains and how
far that sits from a reference vocal balance. Turning measurements into advice is
`merger.py`'s job.

The reference constants below encode a mixed-and-balanced lead vocal. They are
deliberately kept in one place because Phase 1's validation gate is mostly about
tuning them against real recordings.
"""

from __future__ import annotations

import numpy as np
import librosa

from app.models.schemas import (
    BandScore,
    DynamicRange,
    NoiseFloor,
    PitchStability,
    RoomQuality,
    Severity,
    SibilanceProfile,
    SpectralFeatures,
)

SAMPLE_RATE = 44100
N_FFT = 4096
HOP_LENGTH = 1024

#: Bands we score, in Hz. Names double as the keys of `VocalProfile.frequency_bands`.
BANDS: dict[str, tuple[float, float]] = {
    "low_mid": (200.0, 500.0),
    "boxiness": (800.0, 1200.0),
    "presence": (2000.0, 5000.0),
    "air": (6000.0, 10000.0),
    "ultra_high": (10000.0, 16000.0),
}

#: Share of 60 Hz-16 kHz energy each band carries in a well-balanced vocal.
REFERENCE_BALANCE: dict[str, float] = {
    "low_mid": 0.34,
    "boxiness": 0.090,
    "presence": 0.060,
    "air": 0.012,
    "ultra_high": 0.004,
}

#: |deviation| in dB at which a band becomes MODERATE, then CRITICAL.
BAND_MODERATE_DB = 3.0
BAND_CRITICAL_DB = 6.0

ANALYSIS_LOW_HZ = 60.0
ANALYSIS_HIGH_HZ = 16000.0

#: A codec or a low sample rate leaves a cliff: this much drop across this narrow a span,
#: with nothing above it ever recovering. Phone recordings and lossy sources stop dead
#: well below Nyquist, and a band that is simply not there must not be scored as a
#: deficit — no EQ recovers content that was never captured.
CLIFF_DROP_DB = 20.0
CLIFF_WINDOW_HZ = 1000.0
#: A source that stops below this is band-limited: no EQ will recover what is missing.
BAND_LIMIT_HZ = 14000.0
#: A band is only scored when at least this much of it lies inside the usable bandwidth.
MIN_BAND_COVERAGE = 0.75

#: A frame counts as vocal activity if it sits within this many dB of the loudest frame.
ACTIVE_RANGE_DB = 35.0

#: Crest factor / passage spread above which compression is worth suggesting.
CREST_COMPRESSION_DB = 18.0
SPREAD_COMPRESSION_DB = 12.0

SIBILANCE_BAND = (5000.0, 10000.0)
SIBILANCE_BODY_BAND = (300.0, 3000.0)
SIBILANCE_MODERATE = 0.020
SIBILANCE_CRITICAL = 0.050

#: Mains hum candidates and how much a bin must stand out from its neighbours.
HUM_FREQS = (50.0, 60.0)
HUM_PROMINENCE_DB = 8.0

PITCH_FMIN = 65.0
PITCH_FMAX = 1000.0
#: Within-note drift worth correcting. Professional takes measure a 7-cent median and
#: 25 at the 99th percentile, so this sits between their p90 and p99.
PITCH_CORRECTION_CENTS = 20.0
#: A pitch change this big, held for this many frames, is a new note rather than
#: vibrato. Six frames is about 140 ms — longer than a vibrato cycle can stay on one
#: side of its centre, so deep vibrato does not get chopped into notes.
NOTE_STEP_CENTS = 60.0
NOTE_SETTLE_FRAMES = 6

ROOM_TREATED_MS = 180.0
#: Which decay in the take stands for the room. The fastest few are noise; the slow
#: ones are the singer's own releases.
ROOM_DECAY_PERCENTILE = 20.0
#: Part of each decay to ignore: the singer's own release at the top, the noise at the
#: bottom. Frames near the floor read high and flatten the fitted decay, but raising
#: this leaves a very live room — where the gaps never get far above the floor — with
#: too few points to fit at all, which is the case that most needs measuring.
RELEASE_SKIP_DB = 5.0
FLOOR_MARGIN_DB = 5.0

_EPS = 1e-12


class AudioTooShortError(ValueError):
    """Raised when a clip is too short to measure anything meaningful."""


def load_audio(path: str, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Load `path` as mono float32 at `sample_rate`."""
    y, sr = librosa.load(path, sr=sample_rate, mono=True)
    if y.size < sr:  # under a second there is nothing to say
        raise AudioTooShortError(
            f"clip is {y.size / sr:.2f}s; at least 1.0s of audio is required"
        )
    return y.astype(np.float32), sr


def analyze(path: str, sample_rate: int = SAMPLE_RATE) -> SpectralFeatures:
    """Extract the full spectral feature set from an audio file."""
    y, sr = load_audio(path, sample_rate)
    return analyze_samples(y, sr)


def analyze_samples(y: np.ndarray, sr: int) -> SpectralFeatures:
    """Same as `analyze`, but for samples already in memory (used by tests)."""
    spec = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP_LENGTH)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    frame_db = _frame_db(spec)
    active = _active_frames(frame_db)

    bandwidth_hz = _bandwidth_hz(spec[:, active], freqs)
    # Pitch tracking is the expensive pass and both pitch and room analysis need its
    # voicing decisions, so it runs once here.
    f0, voiced, _ = librosa.pyin(
        y, fmin=PITCH_FMIN, fmax=PITCH_FMAX, sr=sr, frame_length=N_FFT, hop_length=HOP_LENGTH
    )

    return SpectralFeatures(
        duration_s=float(y.size / sr),
        sample_rate=sr,
        bandwidth_hz=bandwidth_hz,
        frequency_bands=_band_scores(spec[:, active], freqs, bandwidth_hz),
        dynamic_range=_dynamic_range(y, frame_db, active),
        noise_floor=_noise_floor(spec, freqs, frame_db, active),
        room_quality=_room_quality(frame_db, sr),
        pitch_stability=_pitch_stability(f0, voiced, sr),
        sibilance=_sibilance(spec[:, active], freqs),
    )


# --- frame bookkeeping -----------------------------------------------------


def _frame_db(spec: np.ndarray) -> np.ndarray:
    """Per-frame broadband level in dB."""
    return 10.0 * np.log10(spec.sum(axis=0) + _EPS)


def _active_frames(frame_db: np.ndarray) -> np.ndarray:
    """Boolean mask of frames loud enough to be vocal, not room tone."""
    active = frame_db > (frame_db.max() - ACTIVE_RANGE_DB)
    if not active.any():  # pathological (silence); fall back to everything
        return np.ones_like(frame_db, dtype=bool)
    return active


def _band_energy(spec: np.ndarray, freqs: np.ndarray, low: float, high: float) -> float:
    """Total energy between `low` and `high` Hz across the given frames."""
    band = (freqs >= low) & (freqs < high)
    if not band.any():
        return 0.0
    return float(spec[band].sum())


# --- individual measurements ----------------------------------------------


def _bandwidth_hz(active_spec: np.ndarray, freqs: np.ndarray) -> float:
    """The frequency above which the source carries nothing at all.

    This looks for the cliff a codec or a low sample rate leaves behind — a drop to a
    floor that never recovers — rather than a fixed level below the spectral peak. A
    vocal's peak is at its fundamental and its top octave is legitimately far below
    that, so a peak-relative threshold calls every bass-heavy take band-limited.
    """
    if active_spec.size == 0:
        return 0.0

    profile = active_spec.mean(axis=1)
    db = 10.0 * np.log10(np.convolve(profile, np.ones(9) / 9, mode="same") + _EPS)

    bin_hz = freqs[1] - freqs[0]
    window = max(1, int(CLIFF_WINDOW_HZ / bin_hz))
    start = int(np.searchsorted(freqs, 2000.0))

    for index in range(start, len(freqs) - window):
        before = np.median(db[max(0, index - window) : index])
        after = np.median(db[index : index + window])
        # A cliff drops steeply and never comes back; a gentle rolloff is the source's
        # own character and still has content an air shelf can lift.
        if before - after > CLIFF_DROP_DB and db[index + window :].max() < before - CLIFF_DROP_DB:
            return float(freqs[index])
    return float(freqs[-1])


def _band_scores(
    active_spec: np.ndarray, freqs: np.ndarray, bandwidth_hz: float
) -> dict[str, BandScore]:
    usable_high = max(min(ANALYSIS_HIGH_HZ, bandwidth_hz), ANALYSIS_LOW_HZ + 1.0)
    total = _band_energy(active_spec, freqs, ANALYSIS_LOW_HZ, usable_high) + _EPS

    energies = {
        name: _band_energy(active_spec, freqs, low, high) / total
        for name, (low, high) in BANDS.items()
    }
    # An absent band is a missing source, not a dull vocal: scoring it would advise
    # boosting content that does not exist.
    scored_names = [
        name
        for name, (low, high) in BANDS.items()
        if (min(high, bandwidth_hz) - low) / (high - low) >= MIN_BAND_COVERAGE
    ]

    # The denominator is the whole usable range, not the sum of the scored bands: a band
    # is part of its own total, so normalising by that set would let a boosted band
    # inflate the denominator and hide the very deviation being measured.
    scores: dict[str, BandScore] = {}
    for name, (low, high) in BANDS.items():
        scored = name in scored_names
        deviation = (
            10.0 * np.log10((energies[name] + _EPS) / REFERENCE_BALANCE[name])
            if scored
            else 0.0
        )
        scores[name] = BandScore(
            band_name=name,
            low_hz=low,
            high_hz=high,
            energy=float(energies[name]),
            deviation_db=float(deviation),
            severity=_severity(abs(deviation), BAND_MODERATE_DB, BAND_CRITICAL_DB),
            scored=scored,
        )
    return scores


def _severity(value: float, moderate: float, critical: float) -> Severity:
    if value >= critical:
        return Severity.CRITICAL
    if value >= moderate:
        return Severity.MODERATE
    return Severity.MINOR


def _dynamic_range(y: np.ndarray, frame_db: np.ndarray, active: np.ndarray) -> DynamicRange:
    active_db = frame_db[active]
    # Frame levels are broadband STFT energy, so anchor the absolute numbers to
    # the waveform and use the frame envelope only for spreads.
    rms = float(np.sqrt(np.mean(y**2) + _EPS))
    peak = float(np.max(np.abs(y)) + _EPS)
    rms_db = 20.0 * np.log10(rms)
    peak_db = 20.0 * np.log10(peak)
    crest = peak_db - rms_db
    spread = float(np.percentile(active_db, 95) - np.percentile(active_db, 10))
    return DynamicRange(
        crest_factor_db=float(crest),
        rms_db=float(rms_db),
        peak_db=float(peak_db),
        loud_quiet_spread_db=spread,
        needs_compression=bool(crest > CREST_COMPRESSION_DB or spread > SPREAD_COMPRESSION_DB),
    )


def _noise_floor(
    spec: np.ndarray, freqs: np.ndarray, frame_db: np.ndarray, active: np.ndarray
) -> NoiseFloor:
    quiet = ~active
    if quiet.sum() < 3:
        # No silence to measure: use the quietest frames we have instead.
        cutoff = np.percentile(frame_db, 10)
        quiet = frame_db <= cutoff

    noise_db = float(np.median(frame_db[quiet]))
    signal_db = float(np.median(frame_db[active]))
    snr = signal_db - noise_db

    quiet_spectrum = spec[:, quiet].mean(axis=1)
    hum_freq = _detect_hum(quiet_spectrum, freqs)
    flatness = _spectral_flatness(quiet_spectrum[(freqs >= 500) & (freqs < 8000)])

    return NoiseFloor(
        snr_db=float(snr),
        noise_floor_db=noise_db,
        has_hum=hum_freq is not None,
        hum_freq_hz=hum_freq,
        has_broadband=bool(snr < 40.0 and flatness > 0.15),
    )


def _detect_hum(spectrum: np.ndarray, freqs: np.ndarray) -> float | None:
    """Return the mains frequency if a narrowband tone sits on 50 or 60 Hz."""
    db = 10.0 * np.log10(spectrum + _EPS)
    for base in HUM_FREQS:
        hits = 0
        for harmonic in (1, 2, 3):
            target = base * harmonic
            near = (freqs > target - 15) & (freqs < target + 15)
            around = (freqs > target - 90) & (freqs < target + 90) & ~near
            if not near.any() or not around.any():
                continue
            if db[near].max() - np.median(db[around]) > HUM_PROMINENCE_DB:
                hits += 1
        if hits >= 2:
            return base
    return None


def _spectral_flatness(spectrum: np.ndarray) -> float:
    """Geometric over arithmetic mean: 1.0 is white noise, near 0 is tonal."""
    if spectrum.size == 0:
        return 0.0
    geo = np.exp(np.mean(np.log(spectrum + _EPS)))
    arith = np.mean(spectrum) + _EPS
    return float(geo / arith)


def _room_quality(frame_db: np.ndarray, sr: int) -> RoomQuality:
    """Estimate the room from the fastest decay in the take, not the average one.

    A falling envelope is ambiguous — it is equally the room ringing and a singer
    releasing a long note — and voicing cannot separate them, because reverb is the
    voice's own harmonics and pitch trackers hear it as voiced. Taking the median of
    every decay made sustained studio takes measure as more reverberant than bedroom
    recordings.

    What is not ambiguous: the room sets a floor on how fast sound can disappear. A
    singer can stop dead, a room cannot, so the quickest decays in a take are the ones
    the room shaped and the slow ones are the singer. Hence a low percentile rather
    than the middle.
    """
    frame_s = HOP_LENGTH / sr
    max_frames = int(1.5 / frame_s)
    floor = float(np.percentile(frame_db, 5))

    tails: list[float] = []
    for start in _decay_starts(frame_db):
        decay = _decay_segment(frame_db, start, max_frames)
        usable = decay >= floor + FLOOR_MARGIN_DB
        times = np.arange(decay.size)[usable] * frame_s
        levels = decay[usable]
        if levels.size < 3 or levels[0] - levels[-1] < 3.0:
            continue
        # Fit the decay slope and extrapolate it to a 20 dB drop (a T20 estimate).
        slope_db_per_s = np.polyfit(times, levels, 1)[0]
        if slope_db_per_s >= -1.0:
            continue
        tails.append(min(20.0 / -slope_db_per_s * 1000.0, 3000.0))

    tail_ms = float(np.percentile(tails, ROOM_DECAY_PERCENTILE)) if tails else 0.0
    reflection = float(np.clip((tail_ms - 100.0) / 500.0, 0.0, 1.0))
    return RoomQuality(
        reverb_tail_ms=tail_ms,
        treated=bool(tail_ms < ROOM_TREATED_MS),
        reflection_level=reflection,
    )


def _decay_segment(frame_db: np.ndarray, start: int, max_frames: int) -> np.ndarray:
    """The falling stretch that follows `start`, stopping when the level turns back up."""
    stop = start + 1
    limit = min(len(frame_db), start + max_frames)
    while stop < limit and frame_db[stop] <= frame_db[stop - 1] + 0.5:
        stop += 1
    return frame_db[start:stop]


def _decay_starts(frame_db: np.ndarray) -> list[int]:
    """The first frame of each loud passage that starts falling away.

    Once a decay is found we skip past it, so one phrase contributes one measurement
    rather than one per frame of its release.
    """
    loud = frame_db.max() - 25.0
    starts: list[int] = []
    index = 1
    while index < len(frame_db) - 2:
        if frame_db[index] >= loud and frame_db[index + 1] < frame_db[index] - 1.0:
            starts.append(index)
            while index < len(frame_db) - 2 and frame_db[index + 1] < frame_db[index]:
                index += 1
        index += 1
    return starts


def _pitch_stability(f0: np.ndarray, voiced: np.ndarray, sr: int) -> PitchStability:
    voiced_ratio = float(np.mean(voiced)) if voiced.size else 0.0
    valid = np.isfinite(f0) & voiced
    if valid.sum() < 8:
        return PitchStability(
            drift_cents=0.0,
            vibrato_rate_hz=None,
            vibrato_consistency=0.0,
            voiced_ratio=voiced_ratio,
            needs_correction=False,
        )

    cents = np.full(f0.shape, np.nan)
    cents[valid] = 1200.0 * np.log2(f0[valid] / PITCH_FMIN)
    drift = _drift_cents(cents, valid, sr)

    voiced_cents = cents[valid]
    # Vibrato is what is left once the local pitch centre is taken out.
    wobble = voiced_cents - _rolling_median(voiced_cents, window=_frames_for(0.25, sr))
    rate, consistency = _vibrato(wobble, sr)

    return PitchStability(
        drift_cents=drift,
        vibrato_rate_hz=rate,
        vibrato_consistency=consistency,
        voiced_ratio=voiced_ratio,
        needs_correction=bool(drift > PITCH_CORRECTION_CENTS),
    )


def _drift_cents(cents: np.ndarray, valid: np.ndarray, sr: int) -> float:
    """How far each sustained note wanders from its own centre, vibrato removed.

    A voiced run is a phrase, not a note. Measuring deviation across a whole run scores
    the melody: any singer moving between notes reads as drift, and a scale reads as
    hundreds of cents of it. So runs are split at the pitch changes first, and drift is
    measured only *within* each note.
    """
    smoothing = _frames_for(0.2, sr)
    per_note: list[float] = []

    for start, stop in _voiced_runs(valid, minimum=smoothing + 2):
        for note_start, note_stop in _notes(cents[start:stop], sr):
            note = _moving_average(cents[start + note_start : start + note_stop], smoothing)
            if note.size == 0:
                continue
            per_note.append(float(np.median(np.abs(note - np.median(note)))))
    return float(np.median(per_note)) if per_note else 0.0


def _notes(cents: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """Split a voiced phrase into notes at the places the pitch steps and stays.

    A step has to hold for `NOTE_SETTLE_FRAMES` to count, so vibrato and the moment of
    a slide between notes do not each become a note of their own.
    """
    minimum = _frames_for(0.15, sr)
    if cents.size < minimum * 2:
        return [(0, cents.size)]

    notes: list[tuple[int, int]] = []
    start = 0
    centre = float(np.median(cents[:minimum]))

    index = minimum
    while index < cents.size - NOTE_SETTLE_FRAMES:
        window = cents[index : index + NOTE_SETTLE_FRAMES]
        if np.all(np.abs(window - centre) > NOTE_STEP_CENTS):
            if index - start >= minimum:
                notes.append((start, index))
            start = index
            centre = float(np.median(window))
            index += NOTE_SETTLE_FRAMES
            continue
        # Track the centre as the note goes on, so a singer sliding slowly flat stays
        # one note and is reported as drift instead of being split into two in-tune
        # notes. Drift itself is measured against the finished note's median, not this.
        centre = float(np.median(cents[start : index + 1]))
        index += 1

    if cents.size - start >= minimum:
        notes.append((start, cents.size))
    return notes or [(0, cents.size)]


def _voiced_runs(valid: np.ndarray, minimum: int) -> list[tuple[int, int]]:
    """Contiguous runs of voiced frames, as [start, stop) index pairs."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, is_voiced in enumerate(valid):
        if is_voiced and start is None:
            start = i
        elif not is_voiced and start is not None:
            if i - start >= minimum:
                runs.append((start, i))
            start = None
    if start is not None and valid.size - start >= minimum:
        runs.append((start, valid.size))
    return runs


def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if values.size < window or window < 2:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="valid")


def _frames_for(seconds: float, sr: int) -> int:
    return max(3, int(seconds * sr / HOP_LENGTH) | 1)


def _rolling_median(values: np.ndarray, window: int) -> np.ndarray:
    half = window // 2
    padded = np.pad(values, half, mode="edge")
    return np.array(
        [np.median(padded[i : i + window]) for i in range(values.size)], dtype=float
    )


def _vibrato(deviation: np.ndarray, sr: int) -> tuple[float | None, float]:
    """Look for a 4-8 Hz modulation in the pitch deviation signal."""
    frame_rate = sr / HOP_LENGTH
    if deviation.size < 16:
        return None, 0.0
    windowed = (deviation - deviation.mean()) * np.hanning(deviation.size)
    magnitude = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(deviation.size, d=1.0 / frame_rate)
    band = (freqs >= 4.0) & (freqs <= 8.0)
    if not band.any() or magnitude.sum() <= 0:
        return None, 0.0
    peak = int(np.argmax(magnitude[band]))
    rate = float(freqs[band][peak])
    consistency = float(magnitude[band][peak] / (magnitude.sum() + _EPS))
    return rate, float(np.clip(consistency * 4.0, 0.0, 1.0))


def _sibilance(active_spec: np.ndarray, freqs: np.ndarray) -> SibilanceProfile:
    sib = _band_energy(active_spec, freqs, *SIBILANCE_BAND)
    body = _band_energy(active_spec, freqs, *SIBILANCE_BODY_BAND) + _EPS
    ratio = sib / body

    window = (freqs >= 4000.0) & (freqs <= 11000.0)
    mean_energy = active_spec[window].mean(axis=1)
    peak_freq = float(freqs[window][int(np.argmax(mean_energy))]) if window.any() else 0.0

    return SibilanceProfile(
        ratio=float(ratio),
        peak_freq_hz=peak_freq,
        severity=_severity(ratio, SIBILANCE_MODERATE, SIBILANCE_CRITICAL),
    )
