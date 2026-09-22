# VoxChain

Analyses a vocal recording and recommends plugin chains at three price tiers.
See `CLAUDE.md` for the architecture and the build order.

**Status: Phases 1-2 done.** Backend CLI only, no UI. The analysis pipeline
(detection, spectral measurement, LLM listening pass, merge) and the
recommendation engine (74-plugin catalog, three tiered signal chains) are in
place; the web UI and source separation are Phases 3-4.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"
export GEMINI_API_KEY=...        # optional; without it the listening pass is skipped
cd backend && python -m app.db.seed    # only needed if data/plugins.json changed
```

## Analysing a recording

```bash
cd backend
python -m app.cli take.wav --genre "bedroom rap"
python -m app.cli take.wav --no-llm --json result.json   # measurements only
python -m app.cli take.wav --tier FREE                   # one tier
python -m app.cli take.wav --no-chains                   # analysis only
```

The CLI prints the detected source type, a frequency-balance readout, the raw
measurements, the merged issue list and then one signal chain per price tier.
`--json` writes the whole `AnalysisResult` (profile plus chains).

## What the pipeline does

| Step | Module | Output |
| --- | --- | --- |
| Classify the upload | `analysis/detector.py` | dry vocal vs full mix, with reasons |
| Measure the signal | `analysis/spectral.py` | band balance, dynamics, noise, room, pitch, sibilance |
| Listen to it | `analysis/qualitative.py` | Gemini 2.5 Pro's structured assessment |
| Reconcile the two | `analysis/merger.py` | `VocalProfile` with issues and confidence scores |
| Decide the processing | `recommendation/engine.py` | ordered steps with settings derived from the evidence |
| Fill each step | `recommendation/chain_builder.py` | three `SignalChain`s, one per price tier |

Measured and heard issues that name the same problem merge into one issue at high
confidence, taking the worse of the two severities. Either pass alone still
produces issues, at lower confidence — so the tool degrades to measurements only
when `GEMINI_API_KEY` is absent or the API call fails.

## Recommendations

`engine.py` decides *what* processing the take needs and how to set it, from the
measured evidence — a 4.5 dB low-mid excess becomes "wide bell, Q 1.0, -4.5 dB,
sweep 200-500 Hz". `chain_builder.py` then decides *which plugin* fills each step
at each tier, so the advice does not change when the catalog does.

One step per role: every subtractive cut lands in a single corrective-EQ step,
because that is how one EQ instance gets used. Chain order follows the spec
(cleanup → corrective EQ → compression → tone EQ → de-ess → saturation → space),
with tuning early on the cleaned signal, peak control last, and one exception —
**critical** sibilance moves the de-esser ahead of the compressor, so the
compressor is not riding the esses.

Two selection rules are worth knowing: a plugin tagged `cut-only` (soothe2,
Gullfoss) is never picked for a boost slot, and an EQ may appear twice in one
chain as a second instance rather than forcing a worse plugin into the tone slot.
If a category has nothing at the requested tier, the pick falls back to another
tier and says so in its `why`.

### Catalog

`data/plugins.json` is the source of truth; `app/db/plugins.db` is generated from
it by `python -m app.db.seed` and checked in. `--check` validates without writing
and prints a category × tier coverage table. Validation enforces unique
(name, category) pairs and that each plugin's price actually falls in its tier's
bracket.

Prices are approximate full MSRP captured in 2026-09 for tiering purposes only —
these vendors discount constantly, so verify before treating a number as fact.
`purchase_url` points at the vendor, not a deep product link, because product
URLs rot.

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
