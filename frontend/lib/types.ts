/**
 * Mirrors `backend/app/models/schemas.py`. Kept hand-written rather than generated:
 * the shapes are small and stable, and a generator would be more machinery than the
 * problem needs. If the Pydantic models change, these change with them.
 */

export type Severity = "MINOR" | "MODERATE" | "CRITICAL";

export type ProcessingCategory =
  | "EQ"
  | "COMPRESSION"
  | "DE_ESS"
  | "SATURATION"
  | "GATE"
  | "NOISE_REDUCTION"
  | "PITCH_CORRECTION"
  | "REVERB"
  | "DELAY"
  | "LIMITER";

export type Tier = "FREE" | "MID" | "PREMIUM";

export type SourceType = "DRY_VOCAL" | "FULL_MIX";

export interface BandScore {
  band_name: string;
  low_hz: number;
  high_hz: number;
  energy: number;
  deviation_db: number;
  severity: Severity;
  /** False when the source carries no content in this band, so it was not judged. */
  scored: boolean;
}

export interface DynamicRange {
  crest_factor_db: number;
  rms_db: number;
  peak_db: number;
  loud_quiet_spread_db: number;
  needs_compression: boolean;
}

export interface NoiseFloor {
  snr_db: number;
  noise_floor_db: number;
  has_hum: boolean;
  hum_freq_hz: number | null;
  has_broadband: boolean;
}

export interface RoomQuality {
  /** Estimated RT60 in ms. */
  reverb_tail_ms: number;
  treated: boolean;
  reflection_level: number;
  /** "note transitions", "phrase ends" or "none". */
  measurement: string;
  probes: number;
}

export interface PitchStability {
  drift_cents: number;
  vibrato_rate_hz: number | null;
  vibrato_consistency: number;
  voiced_ratio: number;
  needs_correction: boolean;
}

export interface SibilanceProfile {
  ratio: number;
  peak_freq_hz: number;
  severity: Severity;
}

export interface SourceDetection {
  source_type: SourceType;
  confidence: number;
  sub_bass_ratio: number;
  percussive_ratio: number;
  onset_rate_hz: number;
  reasons: string[];
}

export interface VocalIssue {
  name: string;
  category: ProcessingCategory;
  severity: Severity;
  confidence: number;
  description: string;
  spectral_evidence: Record<string, unknown> | null;
  /** Which analyses raised it: "spectral", "qualitative", or both. */
  sources: string[];
}

export interface VocalProfile {
  source: SourceDetection;
  bandwidth_hz: number;
  frequency_bands: Record<string, BandScore>;
  dynamic_range: DynamicRange;
  noise_floor: NoiseFloor;
  room_quality: RoomQuality;
  pitch_stability: PitchStability;
  sibilance: SibilanceProfile;
  issues: VocalIssue[];
  /** 0-100 per radar axis, computed server-side so thresholds live in one place. */
  scores: Record<string, number>;
  qualitative_summary: string;
  genre: string | null;
  analysis_notes: string[];
}

export interface PluginRecommendation {
  plugin_name: string;
  tier: Tier;
  category: ProcessingCategory;
  suggested_settings: string;
  why: string;
  price: string;
  purchase_url: string | null;
}

export interface SignalChain {
  tier: Tier;
  steps: PluginRecommendation[];
}

export interface AnalysisResult {
  profile: VocalProfile;
  chains: SignalChain[];
}

export const TIERS: Tier[] = ["FREE", "MID", "PREMIUM"];

export const TIER_LABELS: Record<Tier, string> = {
  FREE: "Free",
  MID: "Mid ($30-100)",
  PREMIUM: "Premium ($100+)",
};

export const SEVERITY_ORDER: Record<Severity, number> = {
  MINOR: 0,
  MODERATE: 1,
  CRITICAL: 2,
};
