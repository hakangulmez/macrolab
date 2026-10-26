import type { AnalysisConfig, CountryResult, JsonRecord } from "./types";
import { record, records, strings } from "./format";

/** Round padded presentation bounds outward; never force an unobserved zero. */
export function relationshipExtent(values: number[]) {
  const finite = values.filter(Number.isFinite);
  const low = finite.length ? Math.min(...finite) : 0;
  const high = finite.length ? Math.max(...finite) : 1;
  const padding = (high - low || Math.abs(low) || 1) * 0.05;
  const rawStep = (high - low + 2 * padding) / 5;
  const power = 10 ** Math.floor(Math.log10(rawStep));
  const step =
    ([1, 2, 2.5, 5, 10].find((v) => v * power >= rawStep) ?? 10) * power;
  // Limit floating-point display noise without touching the plotted observations.
  const rounded = (v: number) => Number(v.toPrecision(14));
  return {
    min: rounded(Math.floor((low - padding) / step) * step),
    max: rounded(Math.ceil((high + padding) / step) * step),
    step: rounded(step),
  };
}
export function relationshipEligible(config: AnalysisConfig, r: CountryResult) {
  return (
    r.status === "ok" &&
    ((r.model_id === "sing.ols" &&
      config.series.filter((s) => s.role === "regressor").length === 1) ||
      (r.model_id === "panel.fe" &&
        config.model.params.template_id === "ea_phillips_pooled" &&
        record(r.panel).effects === "country"))
  );
}

export function forecastViewData(result: CountryResult, horizon: number) {
  const e = record(result.evaluation);
  const stored = records(e.predictions)
    .filter((r) => r.horizon === horizon)
    .map((r) => ({
      Period: r.target,
      Origin: r.origin,
      Actual: r.actual,
      ...record(r.predictions),
    }));
  const dates = stored.map((r) => String(r.Period)).sort();
  const match = dates[0]?.match(/^(\d{4})-(Q)?(\d{1,2})$/);
  const rows: JsonRecord[] = [];
  if (match) {
    const quarters = Boolean(match[2]),
      perYear = quarters ? 4 : 12;
    const index = (value: string) => {
      const a = value.match(/^(\d{4})-(?:Q)?(\d{1,2})$/)!;
      return Number(a[1]) * perYear + Number(a[2]) - 1;
    };
    for (let i = index(dates[0]); i <= index(dates.at(-1)!); i++) {
      const period = `${Math.floor(i / perYear)}-${quarters ? "Q" : ""}${quarters ? (i % perYear) + 1 : String((i % perYear) + 1).padStart(2, "0")}`;
      rows.push(
        stored.find((r) => r.Period === period) ?? {
          Period: period,
          Origin: null,
          Actual: null,
          ...Object.fromEntries(strings(e.models).map((m) => [m, null])),
        },
      );
    }
  } else rows.push(...stored);
  return { rows, metrics: records(e.metrics), models: strings(e.models) };
}
