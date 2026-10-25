export type JsonRecord = Record<string, unknown>;
export type Screen =
  "home" | "builder" | "library" | "results" | "catalogue" | "data" | "methods";
export interface SeriesSpec {
  concept_id: string;
  role: string;
  transform: string;
  transform_params?: JsonRecord;
}
export interface AnalysisConfig {
  schema_version: number;
  snapshot_id: string;
  countries: string[];
  series: SeriesSpec[];
  frequency: string;
  aggregation: Record<string, string>;
  sample: { start: string; end: string };
  special_periods: {
    covid: string;
    elb_threshold?: number;
    covid_window?: { start: string; end: string };
  };
  model: { id: string; params: JsonRecord };
  identification: { id: string; params: { order: string[] } } | null;
  outputs: {
    confidence?: number;
    irf?: {
      horizon: number;
      bands: number;
      shock_size: number;
      method: string;
      draws: number;
      shock_mode?: string;
    };
  };
  comparison: {
    enabled?: boolean;
    methods?: string[];
    identifications?: string[];
    scenarios?: string[];
  };
  seed: number;
}
export interface Country extends JsonRecord {
  iso3: string;
  name: string;
  region?: string;
  monetary_union?: string | null;
  currency?: string;
  notes?: unknown[];
  latest_profiles?: JsonRecord[];
  policy_rate_shared?: boolean;
}
export interface Indicator extends JsonRecord {
  concept_id: string;
  title: string;
  category?: string;
  scope?: string;
  default_transform?: string;
  definition?: string;
  frequency?: string;
}
export interface Model extends JsonRecord {
  id: string;
  title: string;
  family: string;
  summary: string;
  label: string;
  assumptions: string[];
  inputs: JsonRecord;
  params: { properties?: Record<string, JsonRecord> };
  references: { title: string; url: string }[];
  runtime: string;
  available?: boolean;
  checks?: Check[];
}
export interface Template extends JsonRecord {
  id: string;
  title: string;
  description: string;
  config: AnalysisConfig;
}
export interface Manifest extends JsonRecord {
  publication?: {
    mode: "static_candidate";
    source_mode?: "cleared" | "all";
    local_only_comparison?: boolean;
    approved: false;
    notes_withheld: boolean;
    excluded_sources: JsonRecord[];
    included_global_factors?: string[];
    excluded_concepts?: { concept_id: string; title: string; reason: string }[];
    excluded_observations: number;
    policy_sha256: string;
  };
  snapshot_id: string;
  as_of_date: string;
  countries: Country[];
  indicators: Indicator[];
  templates: Template[];
  models: Model[];
  validation: JsonRecord;
  sources: JsonRecord[];
  schema_url: string;
}
export interface Card extends Indicator {
  status: string;
  first_date: string | null;
  last_date: string | null;
  sources: string[];
  source_segments: JsonRecord[];
  flags: string[];
  warnings: string[];
  reason_codes: string[];
  stale: boolean;
  policy_label?: string | null;
}
export interface CountryBundle extends JsonRecord {
  country: Country;
  cards: Card[];
  profiles: JsonRecord[];
  series: Record<string, unknown[]>;
  snapshot_id: string;
}
export interface Check extends JsonRecord {
  phase?: "preflight" | "pre_estimation" | "post_estimation";
  level: string;
  code: string;
  message: string;
  country?: string;
  concept_id?: string;
  fix?: JsonRecord | null;
}
export interface Sample extends JsonRecord {
  start: string | null;
  end: string | null;
  nobs: number;
  common_nobs: number;
  periods: string[];
  dropped_periods: JsonRecord[];
  frequency_conversion: JsonRecord;
  transforms: JsonRecord;
}
export interface Coefficient extends JsonRecord {
  term: string;
  estimate: number;
  lower?: number;
  upper?: number;
  std_error?: number;
  p_value?: number;
  equation?: string;
}
export interface IRF extends JsonRecord {
  periods: number[];
  variables: string[];
  values: number[][];
  lower: number[][];
  upper: number[][];
  shock: string;
  shock_size: number;
  band_level: number;
  band_method: string;
}
export interface CountryResult extends JsonRecord {
  country: string;
  model_id: string;
  status: string;
  label: string;
  checks: Check[];
  actual_sample: Sample;
  coefficients_table?: Coefficient[];
  irf?: IRF;
  notes?: string[];
  diagnostics?: JsonRecord;
  sensitivity: {
    reason?: string;
    status: string;
    variants: JsonRecord[];
    summary?: JsonRecord[];
    comparison_rule?: string;
    limitations?: string[];
  };
  filtered_series?: JsonRecord[];
  test_results?: JsonRecord[];
}
export interface AnalysisResult extends JsonRecord {
  status: string;
  config_hash: string;
  snapshot_id: string;
  code_version: string;
  runtime_ms: number;
  label: string;
  config: AnalysisConfig;
  checks: Check[];
  results: CountryResult[];
  actual_samples: Record<string, Sample>;
}
