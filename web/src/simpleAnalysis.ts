import type {
  AnalysisConfig,
  Check,
  CountryBundle,
  Manifest,
  SeriesSpec,
  JsonRecord,
} from "./types";
import { countryIndicators } from "./displayLabels";
import { record, records, text, transforms } from "./format";
import { coverage } from "./uiData";

export const questions = [
  ["describe", "Describe"],
  ["compare", "Compare countries"],
  ["relate", "Relate two variables"],
  ["shock", "Trace a shock"],
  ["forecast", "Forecast"],
] as const;
export type Question = (typeof questions)[number][0];
export type BuildMode = "simple" | "advanced";
export const buildModeKey = "macrolab-build-mode";
export function readBuildMode(): BuildMode {
  try {
    return localStorage.getItem(buildModeKey) === "advanced"
      ? "advanced"
      : "simple";
  } catch {
    return "simple";
  }
}
export function saveBuildMode(mode: BuildMode) {
  try {
    localStorage.setItem(buildModeKey, mode);
  } catch {
    /* Session state remains usable. */
  }
}
export function configKey(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(configKey).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => JSON.stringify(k) + ":" + configKey(v))
      .join(",")}}`;
  return JSON.stringify(value);
}
export interface SimpleSelection {
  countries?: string[];
  concepts?: string[];
  preset?: "monetary_policy" | "same_ecb_shock";
}
export function nativeFrequency(m: Manifest, country: string, concept: string) {
  return (
    coverage(m).find((c) => c.country === country && c.concept_id === concept)
      ?.frequency ||
    m.indicators.find((i) => i.concept_id === concept)?.frequency ||
    ""
  );
}
function methodDefaults(m: Manifest, id: string) {
  return Object.fromEntries(
    Object.entries(m.models.find((x) => x.id === id)?.params.properties ?? {})
      .filter(([, p]) => p.default !== undefined)
      .map(([k, p]) => [k, structuredClone(p.default)]),
  );
}
export function freshSimple(
  m: Manifest,
  question: Question,
  selection: SimpleSelection = {},
): AnalysisConfig {
  if (question === "shock") {
    const preset = selection.preset ?? "monetary_policy";
    const c = structuredClone(m.templates.find((t) => t.id === preset)!.config);
    if (selection.countries) c.countries = [...selection.countries];
    return c;
  }
  if (question === "relate") {
    const c = structuredClone(
      m.templates.find((t) => t.id === "phillips_curve")!.config,
    );
    c.countries = selection.countries ?? [...c.countries];
    const ids = selection.concepts ?? c.series.map((s) => s.concept_id);
    c.series = ids.map((id, i) => ({
      concept_id: id,
      role: i === 0 ? "dependent" : "regressor",
      transform:
        m.indicators.find((x) => x.concept_id === id)?.default_transform ??
        "level",
    }));
    c.aggregation = Object.fromEntries(ids.map((id) => [id, "mean"]));
    return c;
  }
  const countries = selection.countries ?? ["CAN"];
  const id = selection.concepts?.[0] ?? "unemp";
  const frequency = nativeFrequency(m, countries[0], id);
  const method =
    question === "describe"
      ? "desc.plot"
      : question === "compare"
        ? "desc.compare"
        : "uni.arima";
  return {
    schema_version: 1,
    snapshot_id: m.snapshot_id,
    countries: [...countries],
    series: [
      {
        concept_id: id,
        role: question === "forecast" ? "dependent" : "response",
        transform:
          question === "compare"
            ? (m.indicators.find((i) => i.concept_id === id)
                ?.default_transform ?? "level")
            : "level",
      },
    ],
    frequency,
    aggregation: { [id]: "mean" },
    sample: {
      start:
        frequency === "M" ? "1999-01" : frequency === "Q" ? "1999-Q1" : "1999",
      end: "latest",
    },
    special_periods: { covid: "include" },
    model: { id: method, params: methodDefaults(m, method) },
    identification: null,
    outputs: { confidence: 0.95 },
    comparison: { enabled: false },
    seed: 20261021,
  };
}
function fillDefaults(target: unknown, defaults: JsonRecord) {
  if (!target || typeof target !== "object" || Array.isArray(target))
    throw new TypeError("Expected a configuration object");
  for (const [key, value] of Object.entries(defaults))
    if (!Object.hasOwn(target, key))
      (target as JsonRecord)[key] = structuredClone(value);
}
/** Recognition only: mirror normalise_config/validated_config on a copy.
 * Keep all explicit/unknown fields; the engine still validates execution.
 */
export function normalisedSimpleCopy(
  m: Manifest,
  config: AnalysisConfig,
): AnalysisConfig {
  const c = structuredClone(config);
  const periods = {
    M: ["1999-01", "2020-01", "2021-06"],
    Q: ["1999-Q1", "2020-Q1", "2021-Q2"],
    A: ["1999", "2020", "2021"],
  }[c.frequency];
  if (!periods || !Array.isArray(c.countries) || !Array.isArray(c.series))
    throw new TypeError("Expected an analysis configuration");
  fillDefaults(c, {
    aggregation: {},
    sample: { start: periods[0], end: "latest" },
    special_periods: { covid: "include" },
    identification: null,
    outputs: {},
    comparison: {},
    seed: 20261021,
  });
  fillDefaults(c.model, { params: {} });
  fillDefaults(c.special_periods, {
    covid_window: { start: periods[1], end: periods[2] },
    elb_threshold: 0.25,
  });
  fillDefaults(c.outputs, {
    confidence: Object.hasOwn(c.model.params, "confidence")
      ? c.model.params.confidence
      : 0.95,
  });
  if (c.identification !== null || Object.hasOwn(c.outputs, "irf")) {
    fillDefaults(c.outputs, { irf: {} });
    fillDefaults(c.outputs.irf, {
      horizon: 12,
      bands: 0.68,
      shock_size: 1,
      shock_mode: "fixed",
      method: "bootstrap",
      draws: 500,
    });
  }
  fillDefaults(c.comparison, {
    enabled: true,
    identifications: [],
    methods: [],
    scenarios: [],
  });
  for (const s of c.series) {
    fillDefaults(s, { transform_params: {} });
    if (s.transform === "hp_cycle")
      fillDefaults(s.transform_params, {
        lamb: { M: 129600, Q: 1600, A: 6.25 }[c.frequency],
        log: false,
      });
    if (s.transform === "hamilton_cycle")
      fillDefaults(s.transform_params, {
        h: { M: 24, Q: 8, A: 2 }[c.frequency],
        p: { M: 12, Q: 4, A: 1 }[c.frequency],
        log: false,
      });
  }
  const properties = m.models.find((x) => x.id === c.model.id)?.params
    .properties;
  if (properties && Object.hasOwn(properties, "confidence"))
    fillDefaults(c.model.params, { confidence: c.outputs.confidence });
  fillDefaults(c.model.params, methodDefaults(m, c.model.id));
  if (
    c.model.id === "cmp.common_shock" ||
    (c.model.id === "panel.lp" && Object.hasOwn(c.model.params, "first_stage"))
  )
    c.model.params.first_stage = normalisedSimpleCopy(
      m,
      c.model.params.first_stage as AnalysisConfig,
    );
  return c;
}
export function simpleQuestion(
  m: Manifest,
  config: AnalysisConfig,
): Question | null {
  let effective: string;
  try {
    effective = configKey(normalisedSimpleCopy(m, config));
  } catch {
    return null;
  }
  const matches = (candidate: AnalysisConfig) =>
    configKey(normalisedSimpleCopy(m, candidate)) === effective;
  for (const [q] of questions) {
    if (
      q !== "shock" &&
      ((q !== "compare" && config.countries.length !== 1) ||
        (q === "relate"
          ? config.series.length > 2
          : config.series.length !== 1))
    )
      continue;
    const selection: SimpleSelection = {
      countries: config.countries,
      concepts: config.series.map((s) => s.concept_id),
    };
    if (q === "shock") {
      for (const preset of ["monetary_policy", "same_ecb_shock"] as const) {
        if (preset === "monetary_policy" && config.countries.join() !== "USA")
          continue;
        if (
          preset === "same_ecb_shock" &&
          config.countries.some(
            (iso) =>
              iso === "EA" ||
              m.countries.find((c) => c.iso3 === iso)?.monetary_union !== "EA",
          )
        )
          continue;
        if (matches(freshSimple(m, q, { ...selection, preset }))) return q;
      }
    } else if (matches(freshSimple(m, q, selection))) return q;
  }
  return null;
}
export type DataAction = "compare" | "stationarity" | "relate" | "build";
export function dataActionConfig(
  m: Manifest,
  action: DataAction,
  country: string,
  concept: string,
  transform: string,
  transformParams: JsonRecord,
): AnalysisConfig {
  const c = freshSimple(
    m,
    action === "relate"
      ? "relate"
      : action === "compare"
        ? "compare"
        : "describe",
    {
      countries: [country],
      concepts: [concept],
    },
  );
  c.series[0].transform = transform;
  c.series[0].transform_params = structuredClone(transformParams);
  if (action === "stationarity")
    c.model = {
      id: "test.adf_kpss_pp",
      params: methodDefaults(m, "test.adf_kpss_pp"),
    };
  return c;
}
export function selectionChecks(
  m: Manifest,
  c: AnalysisConfig,
  nativeComparison = true,
): Check[] {
  const out: Check[] = [];
  const add = (message: string, code: string, level = "block") =>
    out.push({ phase: "preflight", level, code, message });
  if (c.model.id === "desc.compare" && c.countries.length < 2)
    add(
      "Choose at least two compatible economies to compare.",
      "entry_compare_countries",
    );
  if (c.model.id === "sing.ols" && c.series.length < 2)
    add(
      "Choose the second variable (explanatory variable) before running.",
      "entry_second_variable",
    );
  if (!c.countries.length || !c.series.length)
    add("Choose an economy and an indicator.", "entry_required");
  const cells = coverage(m);
  for (const s of c.series)
    for (const iso of c.countries) {
      if (s.concept_id === "identified_impulse") continue;
      const cell = cells.find(
        (x) => x.country === iso && x.concept_id === s.concept_id,
      );
      const label = `${m.countries.find((x) => x.iso3 === iso)?.name ?? iso} · ${countryIndicators(m.indicators, iso).find((x) => x.concept_id === s.concept_id)?.title ?? s.concept_id}`;
      if (!cell?.observations || cell.status === "missing")
        add(
          `${label}: data are missing; no substitute will be used.`,
          "entry_missing",
        );
      if (
        cell?.stale &&
        ["response", "dependent", "shock"].includes(s.role) &&
        c.sample.end === "latest"
      )
        add(
          `${label}: stale input. In Advanced, explicitly restrict the sample to observed periods before running.`,
          "entry_stale",
        );
      if (
        cell &&
        ({ M: 1, Q: 2, A: 3 }[cell.frequency as "M"] ?? 9) >
          ({ M: 1, Q: 2, A: 3 }[c.frequency as "M"] ?? 0)
      )
        add(
          `${label}: ${cell.frequency} data cannot be converted to ${c.frequency}. Choose compatible inputs or set the frequency explicitly in Advanced.`,
          "entry_frequency",
        );
      if (
        nativeComparison &&
        c.model.id === "desc.compare" &&
        cell &&
        cell.frequency !== c.frequency
      )
        add(
          `${label}: comparison requires a shared native frequency; choose an explicit conversion in Advanced.`,
          "entry_compare_frequency",
        );
    }
  if (c.model.id === "uni.arima" && !["M", "Q"].includes(c.frequency))
    add(
      "ARIMA supports monthly or quarterly inputs; annual inputs cannot run.",
      "entry_forecast_frequency",
    );
  return out;
}
export function seriesQuantity(m: Manifest, c: AnalysisConfig, s: SeriesSpec) {
  const name =
    countryIndicators(m.indicators, c.countries[0]).find(
      (i) => i.concept_id === s.concept_id,
    )?.title ?? s.concept_id;
  return `${name} (${transforms[s.transform] ?? s.transform})`;
}
export function simpleSummary(
  m: Manifest,
  c: AnalysisConfig,
  question: Question,
): string {
  const names = c.countries
    .map((iso) => m.countries.find((x) => x.iso3 === iso)?.name ?? iso)
    .join(", ");
  const quantity = seriesQuantity(m, c, c.series[0]);
  const frequency =
    c.frequency === "M"
      ? "monthly"
      : c.frequency === "Q"
        ? "quarterly"
        : "annual";
  const sample = `requested ${c.sample.start}–${c.sample.end} within snapshot ${c.snapshot_id}`;
  if (question === "describe")
    return `Plot ${quantity} for ${names} at ${frequency} frequency (${sample}), reporting the actual longest contiguous sample and dropped periods; gaps can shorten the window.`;
  if (question === "compare")
    return `Compare the mean of ${quantity} across ${names} on their common observed sample (${sample}), ranked highest to lowest; this is descriptive, without confidence intervals.`;
  if (question === "relate")
    return `Estimate quarterly ${quantity} on ${c.series[1] ? seriesQuantity(m, c, c.series[1]) : "an explanatory variable you must choose"}, with an intercept and HAC(4) standard errors, including COVID observations (${sample}); association, not causation.`;
  if (question === "forecast")
    return `Forecast ${quantity} eight ${c.frequency === "Q" ? "quarters" : "months"} ahead using automatic ARIMA selection (${sample}), with 68% and 90% predictive intervals conditional on fitted parameters.`;
  return c.model.id === "cmp.common_shock"
    ? `Trace the same identified ECB DFR shock through ${names} using lag-augmented local projections and conditional HC1 bands (${sample}); full uncertainty remains available on demand.`
    : `Trace a one-standard-deviation policy shock through the existing two-lag US recursive VAR, with Brent and COVID controls and 68% bootstrap bands (${sample}).`;
}
export function entryUnits(
  bundles: Record<string, CountryBundle>,
  c: AnalysisConfig,
  s: SeriesSpec,
) {
  if (s.transform === "yoy_pct" || s.transform === "qoq_saar") return "%";
  const card = bundles[c.countries[0]]?.cards.find(
    (i) => i.concept_id === s.concept_id,
  );
  const segment = records(card?.source_segments)[0];
  const unit = text(
    segment?.unit_label ?? segment?.unit,
    "Source units (see series card)",
  );
  return s.transform === "log" ? `log(${unit})` : unit;
}
export function sourceNotes(
  m: Manifest,
  c: AnalysisConfig,
  bundles: Record<string, CountryBundle>,
) {
  return c.series.flatMap((s) =>
    c.countries.map((iso) => ({
      iso,
      series: s,
      card: bundles[iso]?.cards.find((x) => x.concept_id === s.concept_id),
      global:
        record(m.indicators.find((i) => i.concept_id === s.concept_id))
          .scope === "global",
    })),
  );
}
