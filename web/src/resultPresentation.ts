import type { AnalysisResult, Check, JsonRecord } from "./types";

// Display schemas never rename keys in the scientific result or its exports.
const labels: Record<string, string> = {
  term: "Variable",
  variable: "Variable",
  country: "Country",
  response: "Response",
  estimate: "Estimate",
  std_error: "Std. error",
  lower: "Lower bound",
  upper: "Upper bound",
  p_value: "p-value",
  statistic: "Statistic",
  test: "Test",
  diagnostic: "Diagnostic",
  nobs: "Observations",
  horizon: "Horizon",
  model: "Model",
  rmse: "RMSE",
  mae: "MAE",
};
export function resultTableColumns(rows: JsonRecord[], columns?: string[]) {
  const keys =
    columns ??
    [...new Set(rows.flatMap(Object.keys))].filter((k) =>
      rows.some((r) => ["string", "number", "boolean"].includes(typeof r[k])),
    );
  if (keys.includes("term") && keys.includes("estimate")) {
    const order = [
      "term",
      "estimate",
      "std_error",
      "lower",
      "upper",
      "p_value",
    ];
    return [
      ...order.filter((k) => keys.includes(k)),
      ...keys.filter((k) => !order.includes(k)),
    ];
  }
  return keys;
}
export function resultColumnLabels(columns: string[]) {
  return Object.fromEntries(
    columns.map((key) => [key, labels[key] ?? key.replaceAll("_", " ")]),
  );
}
export function baselineResultChecks(result: AnalysisResult): Check[] {
  const combined = [
    ...result.checks,
    ...result.results.flatMap((r) =>
      r.checks.map((c) => ({
        ...c,
        country: c.country ?? r.country,
        ...(r.outcome && !c.response && !c.concept_id
          ? { response: r.outcome }
          : {}),
      })),
    ),
  ];
  const key = (check: Check) =>
    JSON.stringify(
      Object.fromEntries(
        Object.entries(check).sort(([a], [b]) => a.localeCompare(b)),
      ),
    );
  return [...new Map(combined.map((c) => [key(c), c])).values()];
}
