# VoxChain

Analyses a vocal recording and recommends plugin chains at three price tiers.
See `CLAUDE.md` for the architecture and the build order.

**Status: Phases 1-4 in place.** The analysis pipeline (detection, separation,
spectral measurement, LLM listening pass, merge), the recommendation engine
(74-plugin catalog, three tiered signal chains), `POST /analyze` and the web UI are
all built. What remains is calibration (below) and Phase 5 polish.

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

## API

```bash
cd backend && uvicorn app.main:app --reload
curl -F file=@take.wav -F genre=drill -F use_llm=false localhost:8000/analyze
```

`POST /analyze` takes a multipart upload (`file`, optional `genre`, optional `use_llm`)
and returns the profile and all three chains. Analysis is synchronous — pitch tracking
dominates, and a one-minute take takes a few seconds — so the stage-by-stage progress
the UI shows is driven by the client, not streamed by the server.

Every response uses the same envelope, errors included:

```json
{ "status": "ok",    "data": { "profile": {...}, "chains": [...] } }
{ "status": "error", "message": "..." }
```

Separation runs only when the upload is detected as a full mix, since separating a dry
vocal degrades a clean signal for nothing. It is slow — roughly real time per minute of
audio on CPU — so a mix uploaded through the API holds the request open for minutes;
`separate=false` turns it off. However it goes (off, unavailable, failed, succeeded) the
profile's notes say which audio was actually measured, and a failed separation falls
back to analysing the mix rather than failing the request.

Uploads are refused for an unsupported extension (415), a file over 60 MB (413), and
audio that is empty, unreadable or under a second (422). If the plugin database is
missing, the analysis still returns and the chains come back empty with a note saying
why. `GET /health` and `GET /tiers` round it out.

## What the pipeline does

| Step | Module | Output |
| --- | --- | --- |
| Classify the upload | `analysis/detector.py` | dry vocal vs full mix, with reasons |
| Isolate the vocal | `separation/demucs_runner.py` | vocal stem, but only for a full mix |
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

428 recordings measured across the four corpora. What that run settled, and what it
did not:

**Validated and applied.** Within-note pitch drift measures a 7-cent median across 300
professional takes, p99 of 25 — so `PITCH_CORRECTION_CENTS` at 20 sits between their
p90 and p99, which is where a "worth correcting" threshold belongs. Before the note
segmentation fix the same corpus measured a 201-cent median, because the metric was
scoring melody.

The detector was retuned against labelled vocals and mixes: it now identifies 82% of
full mixes while reading 97% of vocals correctly, against 55%/99% before. Sub-bass
energy turned out to be a far stronger signal than the rest — solo vocals reach 0.8%
below 100 Hz at the 95th percentile — so it now decides on its own at 3%, which the
original design deliberately avoided. The measurement beat the prior.

**Measured, not applied.** VocalSet is vocal *exercises* — sustained vowels, scales,
arpeggios, no consonants — so its band balance and sibilance figures describe held
vowels rather than singing. Its proposed `REFERENCE_BALANCE` would put `air` at 0.0003
and `SIBILANCE_MODERATE` at 0.002, which are properties of the corpus, not of a good
take. Those constants are unchanged and still uncalibrated.

**Still unresolved: the room.** The fastest-decay fix moved the numbers the right way
(VocalSet 292 → 219 ms, vocadito 141 → 95 ms) but the ordering across corpora is still
driven by content, not by room: a take of sustained notes offers no abrupt stop for the
measurement to find. Raising the noise-floor margin to compensate was tried and
reverted — it leaves a very live room, where the gaps never rise far above the floor,
with too few points to fit at all.

The right experiment is ground truth rather than another corpus: convolve dry takes
with impulse responses of published RT60 and check the measured tail tracks the known
value. That is the next piece of work on this metric.

**Two things a corpus cannot settle.** It says what is typical, not what is good — if
the corpus shares a flaw, the constants inherit it. And all four corpora are sung,
mostly Western and mostly solo; rap, screamed and spoken delivery are thin in all of
them, so the reference is weakest where the likely users are. A handful of real takes
with a one-line verdict each remains the check that matters.
