"""Pydantic v2 models for every data shape that crosses a module boundary."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """How badly a detected issue affects the recording."""

    MINOR = "MINOR"
    MODERATE = "MODERATE"
    CRITICAL = "CRITICAL"


class ProcessingCategory(str, Enum):
    """The kind of plugin that addresses an issue."""

    EQ = "EQ"
    COMPRESSION = "COMPRESSION"
    DE_ESS = "DE_ESS"
    SATURATION = "SATURATION"
    GATE = "GATE"
    NOISE_REDUCTION = "NOISE_REDUCTION"
    PITCH_CORRECTION = "PITCH_CORRECTION"
    REVERB = "REVERB"
    DELAY = "DELAY"
    LIMITER = "LIMITER"


class Tier(str, Enum):
    """Price bracket a plugin recommendation belongs to."""

    FREE = "FREE"
    MID = "MID"
    PREMIUM = "PREMIUM"


class SourceType(str, Enum):
    """What the uploaded file turned out to be."""

    DRY_VOCAL = "DRY_VOCAL"
    FULL_MIX = "FULL_MIX"


# --- Spectral analysis -----------------------------------------------------


class BandScore(BaseModel):
    """Energy in one frequency band, relative to a reference vocal balance."""

    band_name: str
    low_hz: float
    high_hz: float
    energy: float = Field(description="Share of total active-frame energy, 0-1")
    deviation_db: float = Field(
        description="Deviation from the reference balance, in dB. Positive = too much."
    )
    severity: Severity


class DynamicRange(BaseModel):
    crest_factor_db: float
    rms_db: float
    peak_db: float
    loud_quiet_spread_db: float = Field(
        description="Spread between the loudest and quietest sung passages, in dB"
    )
    needs_compression: bool


class NoiseFloor(BaseModel):
    snr_db: float
    noise_floor_db: float
    has_hum: bool
    hum_freq_hz: float | None = None
    has_broadband: bool


class RoomQuality(BaseModel):
    reverb_tail_ms: float
    treated: bool
    reflection_level: float = Field(description="0-1, higher means a more live room")


class PitchStability(BaseModel):
    drift_cents: float = Field(description="Median absolute deviation from local pitch centre")
    vibrato_rate_hz: float | None = None
    vibrato_consistency: float = Field(description="0-1, higher is steadier")
    voiced_ratio: float
    needs_correction: bool


class SibilanceProfile(BaseModel):
    ratio: float = Field(description="Sibilant-band energy over body-band energy")
    peak_freq_hz: float
    severity: Severity


class SpectralFeatures(BaseModel):
    """Everything `spectral.py` measures, before any LLM input is considered."""

    duration_s: float
    sample_rate: int
    frequency_bands: dict[str, BandScore]
    dynamic_range: DynamicRange
    noise_floor: NoiseFloor
    room_quality: RoomQuality
    pitch_stability: PitchStability
    sibilance: SibilanceProfile


# --- Qualitative (LLM) analysis -------------------------------------------


class QualitativeIssue(BaseModel):
    """An issue the listening model reported."""

    name: str
    category: ProcessingCategory
    severity: Severity
    description: str


class QualitativeAnalysis(BaseModel):
    """Structured output of the Gemini listening pass."""

    summary: str
    tonal_balance: str
    room_sound: str
    dynamics: str
    artifacts: str
    genre_context: str | None = None
    issues: list[QualitativeIssue] = Field(default_factory=list)


# --- Merged profile --------------------------------------------------------


class VocalIssue(BaseModel):
    """A single detected problem, after reconciling both analyses."""

    name: str
    category: ProcessingCategory
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    spectral_evidence: dict | None = None
    sources: list[str] = Field(
        default_factory=list, description="Which analyses raised it: spectral, qualitative"
    )


class SourceDetection(BaseModel):
    """Output of `detector.py`."""

    source_type: SourceType
    confidence: float = Field(ge=0.0, le=1.0)
    sub_bass_ratio: float
    percussive_ratio: float
    onset_rate_hz: float
    reasons: list[str] = Field(default_factory=list)


class VocalProfile(BaseModel):
    """The unified analysis result the recommendation engine consumes."""

    source: SourceDetection
    frequency_bands: dict[str, BandScore]
    dynamic_range: DynamicRange
    noise_floor: NoiseFloor
    room_quality: RoomQuality
    pitch_stability: PitchStability
    sibilance: SibilanceProfile
    issues: list[VocalIssue]
    qualitative_summary: str
    genre: str | None = None
    analysis_notes: list[str] = Field(default_factory=list)


# --- Plugin catalog --------------------------------------------------------


class PluginEntry(BaseModel):
    """One row of the plugin catalog, as it appears in `data/plugins.json`."""

    name: str
    vendor: str
    category: ProcessingCategory
    tier: Tier
    price_usd: float = Field(ge=0.0)
    price: str
    purchase_url: str | None = None
    rating: float = Field(ge=0.0, le=5.0, description="Editorial pick strength, not a review")
    tags: list[str] = Field(default_factory=list)
    why: str


# --- Recommendations -------------------------------------------------------


class PluginRecommendation(BaseModel):
    plugin_name: str
    tier: Tier
    category: ProcessingCategory
    suggested_settings: str
    why: str
    price: str
    purchase_url: str | None = None


class SignalChain(BaseModel):
    tier: Tier
    steps: list[PluginRecommendation]


class AnalysisResult(BaseModel):
    """What one run of the pipeline produces — the payload of `POST /analyze`."""

    profile: VocalProfile
    chains: list[SignalChain] = Field(default_factory=list)
