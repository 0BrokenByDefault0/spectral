# CLAUDE.md — VoxChain

## What This Is

VoxChain is a web app that analyzes vocal recordings and recommends plugin chains with tiered pricing (Free/Mid/Premium). It combines spectral DSP analysis with LLM-based qualitative listening to produce actionable mixing feedback.

Full spec: `docs/SPEC.md`

## Architecture

Monorepo with two services:

```
voxchain/
├── CLAUDE.md
├── docs/
│   └── SPEC.md                    # Full product spec
├── backend/                       # Python FastAPI
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                # FastAPI app, CORS, routes
│   │   ├── api/
│   │   │   └── analyze.py         # POST /analyze endpoint
│   │   ├── analysis/
│   │   │   ├── spectral.py        # librosa-based spectral feature extraction
│   │   │   ├── qualitative.py     # Gemini 2.5 Pro audio analysis
│   │   │   ├── merger.py          # Reconcile spectral + qualitative outputs
│   │   │   └── detector.py        # Vocal vs full-mix auto-detection
│   │   ├── separation/
│   │   │   └── demucs_runner.py   # Demucs v4 vocal isolation
│   │   ├── recommendation/
│   │   │   ├── engine.py          # Maps vocal profile → plugin chains
│   │   │   └── chain_builder.py   # Assembles ordered signal chains per tier
│   │   ├── db/
│   │   │   ├── plugins.db         # SQLite plugin catalog
│   │   │   └── seed.py            # Plugin DB seed script
│   │   └── models/
│   │       └── schemas.py         # Pydantic models for all data shapes
│   └── tests/
├── frontend/                      # Next.js + Tailwind
│   ├── package.json
│   ├── app/
│   │   ├── page.tsx               # Upload screen
│   │   └── results/
│   │       └── page.tsx           # Results screen (profile + chain diagram)
│   ├── components/
│   │   ├── UploadZone.tsx
│   │   ├── ProcessingProgress.tsx
│   │   ├── VocalProfileCard.tsx
│   │   ├── IssueList.tsx
│   │   └── ChainDiagram.tsx       # React Flow node graph
│   └── lib/
│       └── api.ts                 # Backend API client
└── data/
    └── plugins.json               # Plugin catalog source (seeds the DB)
```

## Tech Stack

- **Frontend:** Next.js 14+ (App Router), Tailwind CSS, React Flow (chain diagram), Recharts (radar chart)
- **Backend:** Python 3.11+, FastAPI, Pydantic v2
- **Audio Analysis:** librosa (spectral), pYIN (pitch tracking)
- **Source Separation:** Demucs v4 (Meta) — CPU mode fine for V1
- **LLM:** Gemini 2.5 Pro via google-genai SDK — native audio input
- **Database:** SQLite via sqlite3 — plugin catalog
- **Deployment:** Vercel (frontend), Railway or Fly.io (backend)

## Build Order (Follow These Phases)

### Phase 1 — Proof of Concept (START HERE)
Backend CLI only. No UI.
1. Set up FastAPI project with pyproject.toml
2. Write `spectral.py` — take a WAV, extract: frequency band energy scores (200-500Hz, 800-1.2kHz, 2-5kHz, 6-10kHz, 10kHz+), crest factor, noise floor (SNR), sibilance ratio, pitch stability via pYIN
3. Write `qualitative.py` — send audio to Gemini 2.5 Pro, structured JSON response evaluating tonal balance, room sound, dynamics, artifacts, genre-aware context
4. Write `merger.py` — reconcile both outputs into a unified VocalProfile with issues, severity ratings, confidence scores
5. Write `detector.py` — heuristic to classify upload as dry vocal vs full mix (sub-100Hz energy + transient detection)
6. Test with 3-5 diverse vocal recordings (rap, sung, bedroom, treated room)
7. **Validation gate:** Does the merged profile produce mixing advice a real engineer would agree with? If not, iterate here before moving on.

### Phase 2 — Plugin Database + Recommendation Engine
1. Build `plugins.json` with 60-80 plugins across categories (EQ, Compressor, De-esser, Saturator, Gate, Pitch Correction, Reverb, Delay, Limiter, Noise Reduction) and tiers (Free, Mid $30-100, Premium $100+)
2. Write `seed.py` to load JSON into SQLite
3. Write `engine.py` — map each vocal issue to processing categories, select best plugin per tier per category
4. Write `chain_builder.py` — assemble ordered chains following: Gate/NR → Subtractive EQ → Compression → Additive EQ → De-ess → Saturation → Spatial. Adjust order based on issue severity.
5. Output: three complete signal chains (one per tier), each a coherent flow

### Phase 3 — Web UI
1. Scaffold Next.js app with Tailwind
2. Upload screen — drag-and-drop zone, file info display, optional genre tag
3. Processing screen — stage-by-stage progress (Separating → Analyzing → Diagnosing → Building Chain)
4. Results screen:
   - VocalProfileCard — plain-language summary + radar chart (clarity, dynamics, noise, room, sibilance, tonal balance)
   - IssueList — expandable cards with severity badges and explanations
   - ChainDiagram — React Flow horizontal node graph, three tier tabs, expandable nodes with plugin details and settings
5. Connect to backend via `/analyze` endpoint

### Phase 4 — Source Separation
1. Integrate Demucs v4 into the pipeline
2. Auto-detect vocal vs mix using `detector.py`
3. Run Demucs on detected mixes, pass vocal stem to analysis
4. Modify Gemini prompt to note when vocal was extracted (expect minor artifacts)

### Phase 5 — Polish + Ship
1. Error handling: short clips, silence, non-vocal audio, API failures
2. Loading states and timeouts
3. Desktop-first responsive layout
4. Deploy frontend to Vercel, backend to Railway/Fly.io
5. Environment variables: GEMINI_API_KEY

## Key Data Shapes

```python
# VocalProfile — output of the analysis engine
class VocalProfile:
    frequency_bands: dict[str, BandScore]  # band_name → {energy, deviation, severity}
    dynamic_range: DynamicRange            # crest_factor, rms, peak, needs_compression
    noise_floor: NoiseFloor                # snr_db, has_hum, has_broadband
    room_quality: RoomQuality              # reverb_tail_ms, treated, reflection_level
    pitch_stability: PitchStability        # drift_cents, vibrato_consistency, needs_correction
    sibilance: SibilanceProfile            # ratio, peak_freq, severity
    issues: list[VocalIssue]               # merged issue list with confidence scores
    qualitative_summary: str               # LLM's natural-language assessment

# VocalIssue — a single detected problem
class VocalIssue:
    name: str                    # e.g. "Low-Mid Buildup"
    category: ProcessingCategory # EQ, COMPRESSION, DE_ESS, etc.
    severity: Severity           # MINOR, MODERATE, CRITICAL
    confidence: float            # 0-1, higher when both analyses agree
    description: str             # Plain-language explanation
    spectral_evidence: dict | None  # Supporting data from spectral analysis

# PluginRecommendation — a single node in the chain
class PluginRecommendation:
    plugin_name: str
    tier: Tier                   # FREE, MID, PREMIUM
    category: ProcessingCategory
    suggested_settings: str      # Natural-language setting description
    why: str                     # Why this plugin for this issue
    price: str
    purchase_url: str | None

# SignalChain — a complete processing chain at one tier
class SignalChain:
    tier: Tier
    steps: list[PluginRecommendation]  # Ordered signal flow
```

## Environment Variables

```
GEMINI_API_KEY=           # Google AI API key for Gemini 2.5 Pro
```

## Conventions

- Python: use Pydantic v2 models for all data shapes, type hints everywhere
- Frontend: App Router, server components where possible, client components for interactive pieces
- All API responses use consistent JSON envelope: `{ "status": "ok", "data": {...} }` or `{ "status": "error", "message": "..." }`
- Plugin DB is a checked-in SQLite file seeded from `plugins.json` — treat `plugins.json` as the source of truth
- No auth in V1 — it's a tool, not a platform

## What NOT To Build

- No real-time audio processing or monitoring
- No in-app audio playback with effects applied
- No plugin marketplace or checkout
- No user accounts in V1
- No mobile layout in V1 (desktop-first)
