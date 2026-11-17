import data from "./data/report-timeline-pilot.json";
import reviewed from "./data/report-timeline-reviewed.json";
import regions from "./data/report-timeline-regions.json";
import countries from "./data/report-timeline-countries.json";
import { record } from "./format";
import type { AnalysisResult } from "./types";

export type ReportTopic =
  | "inflation"
  | "policy_rate"
  | "growth"
  | "labour"
  | "credit"
  | "exchange_rate"
  | "fiscal"
  | "trade";
export const reportCountries = [
  "USA",
  "EA",
  "TUR",
  "AUS",
  "AUT",
  "BEL",
  "CAN",
  "CHL",
  "COL",
  "CRI",
  "CZE",
  "DNK",
  "EST",
  "FIN",
  "FRA",
  "DEU",
  "GRC",
  "HUN",
  "ISL",
  "IRL",
  "ISR",
  "ITA",
  "JPN",
  "KOR",
  "LVA",
  "LTU",
  "LUX",
  "MEX",
  "NLD",
  "NZL",
  "NOR",
  "POL",
  "PRT",
  "SVK",
  "SVN",
  "ESP",
  "SWE",
  "CHE",
  "GBR",
] as const;
export type ReportCountry = (typeof reportCountries)[number];
export const reportCountryNames: Record<ReportCountry, string> = {
  USA: "United States",
  EA: "Euro area",
  TUR: "Türkiye",
  AUS: "Australia",
  AUT: "Austria",
  BEL: "Belgium",
  CAN: "Canada",
  CHL: "Chile",
  COL: "Colombia",
  CRI: "Costa Rica",
  CZE: "Czechia",
  DNK: "Denmark",
  EST: "Estonia",
  FIN: "Finland",
  FRA: "France",
  DEU: "Germany",
  GRC: "Greece",
  HUN: "Hungary",
  ISL: "Iceland",
  IRL: "Ireland",
  ISR: "Israel",
  ITA: "Italy",
  JPN: "Japan",
  KOR: "Korea",
  LVA: "Latvia",
  LTU: "Lithuania",
  LUX: "Luxembourg",
  MEX: "Mexico",
  NLD: "Netherlands",
  NZL: "New Zealand",
  NOR: "Norway",
  POL: "Poland",
  PRT: "Portugal",
  SVK: "Slovak Republic",
  SVN: "Slovenia",
  ESP: "Spain",
  SWE: "Sweden",
  CHE: "Switzerland",
  GBR: "United Kingdom",
};
export interface ReportPassage {
  quote: string;
  url: string;
  chunkId: string;
  section: string | null;
}
export interface ReportNote {
  id: string;
  country: string;
  topics: ReportTopic[];
  kind: string;
  actor?: string;
  referencePeriod?: string;
  title: string;
  summary: string;
  publishedOn: string;
  eventOn: string | null;
  source: {
    institution: string;
    title: string;
    url: string;
    publicationEvidenceUrl: string | null;
    documentId: string;
    chunkId: string;
    section: string | null;
    quote: string;
    passages?: ReportPassage[];
    language?: string;
  };
}
export const reportNotes = [
  ...data.notes,
  ...reviewed.notes,
  ...regions.notes,
  ...countries.notes,
] as ReportNote[];
export const reportCoverage = data.coverage;
export const chronologyCoverage = countries.coverage;

export function resultReportCountries(result: AnalysisResult): ReportCountry[] {
  return reportCountries.filter(
    (country) =>
      result.config.countries.includes(country) &&
      result.results.some((r) => r.country === country && r.status === "ok"),
  );
}

export function reportTopicsForResult(result: AnalysisResult): ReportTopic[] {
  const concepts = new Set(result.config.series.map((s) => s.concept_id));
  const groups: Record<ReportTopic, string[]> = {
    inflation: [
      "cpi",
      "cpi_core",
      "ppi",
      "gdp_defl",
      "ulc",
      "oil_brent",
      "commod_idx",
    ],
    policy_rate: [
      "policy_rate",
      "us_policy_rate",
      "rate_3m",
      "rate_10y",
      "term_spread",
    ],
    growth: [
      "gdp_real",
      "cons_priv",
      "cons_gov",
      "gfcf",
      "ind_prod",
      "retail_vol",
      "cli",
      "conf_bus",
      "conf_cons",
    ],
    labour: ["unemp", "employment", "lfpr", "ulc"],
    credit: ["credit_pnfs", "money_broad", "house_real", "equity_idx"],
    exchange_rate: ["fx_usd", "neer", "reer"],
    fiscal: ["gov_balance", "gov_debt", "cons_gov"],
    trade: ["exports_real", "imports_real", "ca_gdp"],
  };
  return (Object.keys(groups) as ReportTopic[]).filter((topic) =>
    groups[topic].some((concept) => concepts.has(concept)),
  );
}

/** A chronological overview, evenly spaced across distinct reports, not a relevance score. */
export function timelineHighlights(
  notes: ReportNote[],
  limit = 6,
): ReportNote[] {
  if (limit < 1) return [];
  const reports = [
    ...new Map(notes.map((note) => [note.source.documentId, note])).values(),
  ];
  if (reports.length <= limit) return reports;
  if (limit === 1) return [reports[0]];
  return Array.from(
    { length: limit },
    (_, index) =>
      reports[Math.round((index * (reports.length - 1)) / (limit - 1))],
  );
}

/** Calendar boundaries, never a guessed publication date or a shifted horizon. */
export function periodBoundary(value: string | null | undefined, end: boolean) {
  if (!value) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const date = new Date(`${value}T12:00:00Z`);
    return Number.isNaN(date.getTime()) ||
      date.toISOString().slice(0, 10) !== value
      ? null
      : value;
  }
  const quarter = /^(\d{4})-Q([1-4])$/.exec(value);
  const month = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(value);
  const year = /^\d{4}$/.test(value) ? Number(value) : null;
  if (!quarter && !month && year === null) return null;
  const y = Number(quarter?.[1] ?? month?.[1] ?? year);
  const m = quarter
    ? (Number(quarter[2]) - 1) * 3 + (end ? 3 : 1)
    : month
      ? Number(month[2])
      : end
        ? 12
        : 1;
  return new Date(Date.UTC(y, end ? m : m - 1, end ? 0 : 1))
    .toISOString()
    .slice(0, 10);
}

export interface TimelineContext {
  country: ReportCountry;
  topics: ReportTopic[];
  start: string | null;
  end: string | null;
  forecast: boolean;
  message: string | null;
  notes: ReportNote[];
}

export function timelineForResult(
  result: AnalysisResult,
  notes: ReportNote[] = reportNotes,
  selectedCountry?: ReportCountry,
): TimelineContext | null {
  const config = result.config;
  const available = resultReportCountries(result);
  const country = selectedCountry ?? available[0];
  if (!country || !available.includes(country)) return null;
  const local = result.results.find(
    (r) => r.country === country && r.status === "ok",
  )!;
  const topics = reportTopicsForResult(result);
  if (!topics.length) return null;
  const actual = result.actual_samples?.[country] ?? local.actual_sample;
  const startPoints = [
    periodBoundary(config.sample.start, false),
    periodBoundary(actual?.start, false),
  ].filter((d): d is string => Boolean(d));
  const start = startPoints.sort().at(-1) ?? null;
  const endPoints = [
    periodBoundary(config.sample.end, true),
    periodBoundary(actual?.end, true),
  ].filter((d): d is string => Boolean(d));
  const forecast = ["uni.arima", "fc.var", "fc.eval"].includes(config.model.id);
  const base = { country, topics, start, end: null, forecast, notes: [] };
  if (config.model.id === "fc.eval")
    return {
      ...base,
      message:
        "This pilot does not align notes to individual rolling forecast origins. No timeline notes are shown for forecast evaluations.",
    };
  if (forecast) {
    const origin = record(local.forecast).origin;
    const cutoff = periodBoundary(
      typeof origin === "string" ? origin : null,
      true,
    );
    if (!cutoff)
      return {
        ...base,
        message:
          "The forecast origin could not be established. No report notes are shown.",
      };
    endPoints.push(cutoff);
  }
  const end = endPoints.sort()[0] ?? null;
  if (!start || !end || start > end)
    return {
      ...base,
      message:
        "The analysis period could not be established for this timeline.",
    };
  return {
    country,
    topics,
    start,
    end,
    forecast,
    message: null,
    notes: notes
      .filter(
        (n) =>
          n.country === country &&
          /^\d{4}-\d{2}-\d{2}$/.test(n.publishedOn) &&
          periodBoundary(n.publishedOn, false) === n.publishedOn &&
          n.publishedOn >= start &&
          n.publishedOn <= end &&
          n.topics.some((t) => topics.includes(t)),
      )
      .sort((a, b) =>
        `${a.publishedOn}|${a.id}`.localeCompare(`${b.publishedOn}|${b.id}`),
      ),
  };
}

export function chronologyForCountry(
  country: ReportCountry,
  notes: ReportNote[] = reportNotes,
): TimelineContext {
  return {
    country,
    topics: [
      "inflation",
      "policy_rate",
      "growth",
      "labour",
      "credit",
      "exchange_rate",
      "fiscal",
      "trade",
    ],
    start: chronologyCoverage.start,
    end: chronologyCoverage.asOf,
    forecast: false,
    message: null,
    notes: notes
      .filter(
        (note) =>
          note.country === country &&
          periodBoundary(note.publishedOn, false) === note.publishedOn &&
          note.publishedOn >= chronologyCoverage.start &&
          note.publishedOn <= chronologyCoverage.asOf,
      )
      .sort((a, b) =>
        `${a.publishedOn}|${a.id}`.localeCompare(`${b.publishedOn}|${b.id}`),
      ),
  };
}
