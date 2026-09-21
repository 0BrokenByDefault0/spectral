# VoxChain

Analyses a vocal recording and recommends plugin chains at three price tiers.
See `CLAUDE.md` for the architecture and the build order.

**Status: Phase 1 (proof of concept).** Backend CLI only, no UI. The analysis
pipeline — detection, spectral measurement, LLM listening pass, merge — is in
place; the plugin database, recommendation engine, web UI and source separation
are Phases 2-5.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"
export GEMINI_API_KEY=...        # optional; without it the listening pass is skipped
```

## Analysing a recording

```bash
cd backend
python -m app.cli take.wav --genre "bedroom rap"
python -m app.cli take.wav --no-llm --json profile.json   # measurements only
```

The CLI prints the detected source type, a frequency-balance readout, the raw
measurements and the merged issue list. `--json` writes the full `VocalProfile`.

## What the pipeline does

| Step | Module | Output |
| --- | --- | --- |
| Classify the upload | `analysis/detector.py` | dry vocal vs full mix, with reasons |
| Measure the signal | `analysis/spectral.py` | band balance, dynamics, noise, room, pitch, sibilance |
| Listen to it | `analysis/qualitative.py` | Gemini 2.5 Pro's structured assessment |
| Reconcile the two | `analysis/merger.py` | `VocalProfile` with issues and confidence scores |

Measured and heard issues that name the same problem merge into one issue at high
confidence, taking the worse of the two severities. Either pass alone still
produces issues, at lower confidence — so the tool degrades to measurements only
when `GEMINI_API_KEY` is absent or the API call fails.

## Tests

```bash
cd backend && python -m pytest
```

Tests drive the analysis with synthetic signals (`tests/synth.py`) built to carry
the properties being measured — mud, sibilance, hum, reverb, level swings, a drum
loop. They pin down behaviour and direction, not absolute accuracy.

## Calibration status

The reference constants in `spectral.py` (`REFERENCE_BALANCE`, the severity
thresholds, `SIBILANCE_MODERATE`, `ROOM_TREATED_MS`, `PITCH_CORRECTION_CENTS`)
are first-pass values checked only against synthetic signals. **Phase 1's
validation gate — running 3-5 real recordings and confirming an engineer would
agree with the advice — has not been done, and these numbers should be expected
to move when it is.** They are all in one block at the top of the module for
that reason.
