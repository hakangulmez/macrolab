import type { JsonRecord, Indicator, Manifest } from "./types";
export const record = (value: unknown): JsonRecord =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
export const records = (value: unknown): JsonRecord[] =>
  Array.isArray(value) ? value.map(record) : [];
export const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.map(String) : [];
export const text = (value: unknown, fallback = "—"): string =>
  value === undefined || value === null
    ? fallback
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
export const number = (value: unknown, digits = 3): string =>
  typeof value === "number" && Number.isFinite(value)
    ? value !== 0 && Math.abs(value) < 10 ** -digits
      ? value.toExponential(2)
      : new Intl.NumberFormat("en", { maximumFractionDigits: digits }).format(
          value,
        )
    : "—";
/** Table display only. Calculation and export values retain full precision. */
export const significant = (value: unknown): string =>
  typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("en", {
        minimumSignificantDigits: 3,
        maximumSignificantDigits: 3,
        notation: "standard",
      }).format(value)
    : "—";
/** Counts, indices and dates are not estimates: retain their integer precision. */
export const integerField = (key: string): boolean =>
  /^(?:(?:null |suggested |forecast |actual sample |sample |baseline |sign comparison |peak |max |min |minimum |required |selected |common |total |effective |requested |dropped |adf |kpss |hac |dependent |bootstrap |dummy )*(?:horizons?|periods?|quarters?|months?|years?|lags?|observations|nobs|counts?|rank|draws|replications|seed)|n|t|t min|t max|df|df resid|df model|residual df|residual degrees of freedom|effect rank|dk bandwidth|bandwidth|n parameters|num parameters|parameters|parameter count per equation|clusters|design columns|common holdback|comparable alternatives|eligible|numerical retries|redundant nuisance dimensions|unstable draws retained|maxlags|schema version|window)$/i.test(
    key.replaceAll("_", " ").replaceAll("–", " ").trim(),
  );
export const tableValue = (key: string, value: unknown): string =>
  typeof value === "number"
    ? integerField(key)
      ? text(value)
      : significant(value)
    : text(value);
export const horizonAxisTitle = (frequency?: string): string =>
  `${frequency === "M" ? "Months" : frequency === "A" || frequency === "Y" ? "Years" : "Quarters"} after the shock`;
export const title = (id: string, indicators: Indicator[]) =>
  indicators.find((i) => i.concept_id === id)?.title ?? id.replaceAll("_", " ");
export function indicatorSummary(manifest: Manifest): string {
  const national = manifest.indicators.filter(
    (i) => i.scope !== "global",
  ).length;
  const included = manifest.publication?.included_global_factors;
  const localOnly =
    manifest.publication?.local_only_comparison === true ||
    manifest.publication?.source_mode === "all";
  const globals = manifest.indicators.filter(
    (i) =>
      i.scope === "global" &&
      (localOnly || !included || included.includes(i.concept_id)),
  ).length;
  return `${national} indicators + ${globals} ${included && !localOnly ? "included " : ""}global factors`;
}
export const categories: Record<string, string> = {
  activity: "Output & activity",
  prices: "Prices & wages",
  labour: "Labour market",
  money_finance: "Money & finance",
  external: "External sector",
  fiscal: "Fiscal",
  confidence: "Confidence",
  global: "Global factors",
};
export const transforms: Record<string, string> = {
  level: "Level",
  log: "Log level",
  diff: "Quarter/period change",
  log_diff: "Log growth ×100",
  yoy_pct: "Year-on-year growth (%)",
  yoy_diff: "Year-on-year change",
  qoq_saar: "Quarterly growth, annualised",
  index_to_base: "Index to base period",
  hp_cycle: "HP cycle",
  hamilton_cycle: "Hamilton cycle",
};
export const formulas: Record<string, string> = {
  level: "xₜ",
  log: "ln(xₜ)",
  diff: "xₜ − xₜ₋₁",
  log_diff: "100 × [ln(xₜ) − ln(xₜ₋₁)]",
  yoy_pct: "100 × (xₜ / xₜ₋ₛ − 1), s = periods per year",
  yoy_diff: "xₜ − xₜ₋ₛ, s = periods per year",
  qoq_saar: "100 × [(xₜ / xₜ₋₁)⁴ − 1]",
  index_to_base: "100 × xₜ / x_base",
  hp_cycle: "xₜ − HP trendₜ (retrospective)",
  hamilton_cycle: "xₜ − fitted Hamilton trendₜ (retrospective)",
};
export const statusText: Record<string, string> = {
  available: "Available",
  available_note: "Available · note",
  limited: "Limited",
  missing: "Missing",
};
export function download(
  content: Blob | string,
  name: string,
  type = "text/plain",
) {
  const blob =
    typeof content === "string" ? new Blob([content], { type }) : content;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function csv(rows: unknown[][]): string {
  return rows
    .map((row) =>
      row.map((v) => `"${text(v, "").replaceAll('"', '""')}"`).join(","),
    )
    .join("\r\n");
}
