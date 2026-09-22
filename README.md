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

## Band-limited sources

Real home recordings are often phone captures or lossy files delivered in a 44.1 kHz
container, with nothing above 6-10 kHz. Telling somebody to boost 8 kHz on a source
that ends at 8 kHz is advice that can only raise noise, so `spectral.py` measures where
the source actually stops and bands past that are left unscored (`BandScore.scored`).
The profile then says what the real fix is — a better source — instead of prescribing
an EQ move.

The cutoff is found by looking for a *cliff*: a sharp drop that never recovers, which
is what a codec or a low sample rate leaves behind. A gentle rolloff is a dull mic, not
a missing band, and still gets the air shelf — there is signal there to lift.

## Calibration

Constants that decide what counts as a problem have to come from recordings, so
`tools/` measures a labelled corpus and reports what the distributions say those
constants should be.

```bash
cd backend
python -m tools.fetch_mixes --out ~/corpus/mixes --count 40
python -m tools.calibrate measure ~/corpus/VocalSet --label vocalset --limit 300 --out runs.jsonl
python -m tools.calibrate measure ~/corpus/vocadito --label vocadito --out runs.jsonl
python -m tools.calibrate report runs.jsonl
python -m tools.calibrate propose runs.jsonl --reference vocalset --home vocadito --mix mixes
```

`report` prints percentile tables per corpus; `propose` prints the constants those
percentiles imply, each next to its current value. Reference balance comes from the
median of the good-takes corpus, severity thresholds from how much that corpus varies
around its own median, the room threshold from whatever best separates treated from
untreated rooms, and the detector thresholds from where the vocal and mix populations
actually split.

Corpora used, all under licences permitting commercial use, since these constants ship:

| Corpus | Licence | Role |
| --- | --- | --- |
| [VocalSet](https://zenodo.org/records/1193957) | CC BY 4.0 | Studio, dry, professional — the reference for "a good raw take" |
| [vocadito](https://zenodo.org/records/5578807) | CC BY 4.0 | Amateur home recordings — the untreated-room and band-limited cases |
| [Choral Singing Dataset](https://zenodo.org/records/1319597) | CC BY 4.0 | Close-mic'd in a treated room |
| Internet Archive netlabels | CC BY / CC BY-SA / CC0 | Full mixes, for scoring the detector |

MUSDB18 is the obvious corpus for this and is **not** used: its licence forbids
commercial use, and tuning a product's shipped constants on it is exactly that use.
`fetch_mixes.py` enforces the same rule on what it downloads — about one netlabel
release in eight qualifies.

Audio is never committed; only the derived numbers and `fetch_mixes.py`'s attribution
manifest are.

## Calibration status

The reference constants in `spectral.py` (`REFERENCE_BALANCE`, the severity
thresholds, `SIBILANCE_MODERATE`, `ROOM_TREATED_MS`, `PITCH_CORRECTION_CENTS`) are
still first-pass values checked only against synthetic signals. The corpus work above
is how they get replaced, and the first measurements already show the band references
are far off — real solo vocals sit roughly 8-10 dB below the current `presence` and
`air` figures, so almost every honest take would be told it lacks both.

The cause is conceptual as much as numerical: those figures describe a *mixed* vocal
while the input is a *raw take*, which guarantees the deficit. The corpus median of
good studio takes replaces them.

Two things remain open:

- **Nothing here is validated by ear.** A corpus says what is typical, not what is
  good; if a corpus shares a flaw, the constants inherit it. Phase 1's validation gate
  — a handful of real takes where somebody confirms the advice is what they would have
  said — is still the check that matters, and has not been done.
- **The corpora are sung, mostly Western, and mostly solo.** Rap, screamed and spoken
  delivery are thin on the ground in all of them, so the reference is weakest exactly
  where the product's likely users sit.
