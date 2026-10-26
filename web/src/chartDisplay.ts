import type { CountryResult, Indicator } from "./types";
import type { ResultChart } from "./resultData";
import { title } from "./format";

export function screenText(value: string, indicators: Indicator[]): string {
  return value
    .replace(/\b[a-z]+(?:_[a-z0-9]+)*\b/g, (code) =>
      indicators.some((i) => i.concept_id === code)
        ? title(code, indicators)
        : code,
    )
    .replace(/\bunit root Test/g, "Null hypothesis: unit root. Test")
    .replace(/\bstationarity Test/g, "Null hypothesis: stationarity. Test");
}

/** Screen-only wording. Result fields and export serializers remain untouched. */
export function resultDisplayLabel(label: string): string {
  return label.replace(
    "Conditional association to a -1-unit move in neer, controlling for lags",
    "Conditional association to a 1% depreciation (fall in NEER), controlling for lags",
  );
}
export function chartDisplay(
  result: CountryResult,
  chart: ResultChart,
  indicators: Indicator[],
) {
  const id = result.model_id;
  let estimateLabel = "Response",
    comparisonShortLabel = "";
  if (id.startsWith("sing.")) {
    estimateLabel =
      chart.coefficient || chart.name.endsWith("coefficient path")
        ? "Coefficient"
        : chart.name.endsWith("residual")
          ? "Residual"
          : "Observed";
    comparisonShortLabel = "Fitted";
  } else if (id.startsWith("filter.")) {
    estimateLabel = chart.name.endsWith(": cycle") ? "Cycle" : "Observed";
    comparisonShortLabel = "Trend";
  } else if (["var.ols", "ident.recursive"].includes(id)) {
    estimateLabel = "Baseline";
    comparisonShortLabel = "Reversed order";
  } else if (result.pass_through && chart.variable === "cpi") {
    estimateLabel = "Full sample";
    comparisonShortLabel = "Since 2003";
  } else if (chart.name === "Cumulative pass-through ratio")
    estimateLabel = "Pass-through ratio";
  else if (id === "desc.corr") estimateLabel = "Correlation";
  else if (id === "desc.plot") estimateLabel = "Observed";
  else if (id === "desc.compare") estimateLabel = "Observed";
  else if (id.startsWith("test.")) estimateLabel = "Test statistic";
  if (chart.coefficient) estimateLabel = "Coefficient";
  const displaySummary = chart.summary
    .replace(/^unit root Test/, "Null hypothesis: unit root. Test")
    .replace(/^stationarity Test/, "Null hypothesis: stationarity. Test");
  const displayTitle = screenText(chart.name, indicators);
  return { estimateLabel, comparisonShortLabel, displaySummary, displayTitle };
}
export function parameterDisplayLabel(value: string) {
  const labels: Record<string, string> = {
    "driscoll-kraay": "Driscoll–Kraay",
    "country-clustered": "Country-clustered",
    hac: "HAC",
    hc1: "HC1",
    aic: "AIC",
    bic: "BIC",
    hq: "Hannan–Quinn",
    maxlags: "Maximum lags",
    lags: "Lags",
    horizon: "Horizon",
    lambda: "Lambda",
    sample_mode: "Sample window",
    horizon_specific: "Horizon-specific sample",
    common: "Common sample",
    shock_size: "Shock size",
    growth_scale: "Growth scale",
    fixed: "Fixed",
    bootstrap: "Bootstrap",
    confidence: "Confidence level",
    window: "Window",
    step: "Step",
    mode: "Mode",
    rolling: "Rolling window",
    recursive: "Recursive",
    correlation: "Correlation",
    dummies: "Dummies",
    exclude: "Exclude",
    crisis_mode: "Crisis treatment",
  };
  return (
    labels[value] ??
    value.replaceAll("_", " ").replace(/^./, (s) => s.toUpperCase())
  );
}
