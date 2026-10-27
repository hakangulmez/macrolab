import type { AnalysisResult, Manifest, JsonRecord } from "./types";
import { record, records, significant, text } from "./format";
import { termLabel } from "./resultData";
import { countryIndicators } from "./displayLabels";
import { sensitivityDisplayLabel } from "./sensitivityLabels";

/** Display identification only. Never annotates or edits a configuration. */
export function resultTemplate(result: AnalysisResult, manifest: Manifest) {
  const config = result.config;
  return (
    manifest.templates.find((t) => t.id === config.model?.params.template_id) ??
    manifest.templates.find(
      (t) =>
        t.config.model.id === config.model?.id &&
        t.config.countries.join() === config.countries.join() &&
        t.config.series.map((s) => s.concept_id).join() ===
          config.series.map((s) => s.concept_id).join(),
    )
  );
}
function excludes(lower: unknown, upper: unknown) {
  if (typeof lower !== "number" || typeof upper !== "number")
    return "has no reported bounds";
  return lower > 0 || upper < 0 ? "excludes zero" : "includes zero";
}
/** Fixed sentence templates over returned fields; no thresholds or model runs. */
export function keyFacts(result: AnalysisResult, manifest: Manifest): string[] {
  const template = resultTemplate(result, manifest)?.id;
  const r = result.results[0];
  if (!template || !r || r.status !== "ok") return [];
  const country =
    manifest.countries.find((c) => c.iso3 === r.country)?.name ?? r.country;
  const sample = `${r.actual_sample.start}–${r.actual_sample.end}; n = ${r.actual_sample.nobs}`;
  const sampleLine = `Actual sample: ${sample}${r.country === "POOLED" ? " country-period observations" : ""}.`;
  if (template === "ea_inflation_horse_race") {
    const metrics = records(record(r.evaluation).metrics).filter(
      (m) => m.horizon === 1 && typeof m.rmse === "number",
    );
    const winner = metrics.reduce<JsonRecord | undefined>(
      (a, b) => (!a || Number(b.rmse) < Number(a.rmse) ? b : a),
      undefined,
    );
    if (!winner) return [];
    return [
      `At one quarter ahead, ${text(winner.model)} has the lowest reported RMSE, ${significant(winner.rmse)} percentage points, across ${text(winner.n_forecasts)} forecasts.`,
      `Its RMSE relative to the random walk is ${significant(winner.relative_rmse)}; this is pseudo-out-of-sample evaluation using final-vintage data.`,
      `Input sample: ${sample}; each forecast uses its own training prefix.`,
    ];
  }
  if (template === "tur_pass_through") {
    const h = records(record(r.pass_through).horizons).find(
      (row) => row.horizon === 12,
    );
    if (!h) return [];
    const bounds = record(record(h.bands)["0.68"]);
    return [
      `At 12 months, the cumulative CPI / cumulative NEER pass-through ratio is ${significant(h.ratio)} for the same impulse.`,
      `The 68% interval is ${significant(bounds.lower)} to ${significant(bounds.upper)} and ${excludes(bounds.lower, bounds.upper)}.`,
      sampleLine,
    ];
  }
  const terms: Record<string, [string, string]> = {
    taylor_rule: [
      "cpi",
      "A one-percentage-point difference in y/y CPI inflation is associated with a",
    ],
    phillips_curve: [
      "unemp",
      "A one-percentage-point difference in unemployment is associated with a",
    ],
    okuns_law: [
      "gdp_real",
      "A one-percentage-point difference in y/y real GDP growth is associated with a",
    ],
    ea_phillips_pooled: [
      "unemp",
      "A one-percentage-point difference in the HP unemployment gap is associated with a",
    ],
  };
  if (terms[template]) {
    const [term, lead] = terms[template];
    const coef = r.coefficients_table?.find((c) => c.term === term);
    if (!coef) return [];
    const outcome =
      template === "taylor_rule"
        ? "policy rate"
        : template === "okuns_law"
          ? "y/y change in unemployment"
          : template === "ea_phillips_pooled"
            ? "y/y HICP inflation"
            : "y/y CPI inflation";
    const level =
      Number(
        coef.confidence_level ??
          result.config.outputs.confidence ??
          result.config.model.params.confidence ??
          0.95,
      ) * 100;
    return [
      `${lead} ${significant(coef.estimate)} percentage-point difference in ${outcome}.`,
      `The ${level}% coefficient interval is ${significant(coef.lower)} to ${significant(coef.upper)} and ${excludes(coef.lower, coef.upper)}.`,
      sampleLine,
    ];
  }
  if (r.irf) {
    const variable = template === "same_ecb_shock_pooled" ? "cpi" : "gdp_real";
    const j = r.irf.variables.indexOf(variable);
    if (j < 0) return [];
    const values = r.irf.values.map((row) => row[j]);
    const i = values.reduce(
      (best, value, index) =>
        Math.abs(value) > Math.abs(values[best]) ? index : best,
      0,
    );
    const value = values[i],
      horizon = r.irf.periods[i];
    const when = `${horizon} ${horizon === 1 ? "quarter" : "quarters"} after the shock`;
    const response =
      template === "monetary_policy"
        ? `The response of real GDP growth (q/q annualised) ${value < 0 ? "reaches a trough at" : "peaks at"} ${value > 0 ? "+" : ""}${significant(value)} percentage points, ${when}.`
        : `${variable === "cpi" ? "Pooled HICP" : `Real GDP in ${country}`} is ${significant(Math.abs(value))}% ${value < 0 ? "lower" : "higher"} at the ${value < 0 ? "trough" : "peak"}, ${when}.`;
    const lower = r.irf.lower?.[i]?.[j],
      upper = r.irf.upper?.[i]?.[j];
    return [
      response,
      `For a ${significant(r.irf.shock_size)} pp policy-rate shock, the ${Math.round(r.irf.band_level * 100)}% pointwise band there is ${significant(lower)} to ${significant(upper)} and ${excludes(lower, upper)}.`,
      sampleLine,
    ];
  }
  return [];
}

export function robustnessHeadlines(
  result: AnalysisResult,
  manifest: Manifest,
): { line: string; scope: string }[] {
  const flagged = records(result.template_sensitivity)
    .filter(
      (v) =>
        v.same_estimand !== false && v.include_in_agreement_counts !== false,
    )
    .flatMap((v) =>
      records(v.comparison).filter((c) => typeof c.material === "boolean"),
    );
  if (flagged.length) {
    const labels = [
      ...new Set(flagged.map((c) => text(c.outcome ?? c.term))),
    ].map((id) =>
      termLabel(
        id,
        countryIndicators(manifest.indicators, result.config.countries[0]),
      ),
    );
    return [
      {
        line: `${flagged.filter((c) => c.material === false).length} of ${flagged.length} checks hold`,
        scope: `Returned material-change flags for ${labels.join("; ")}${flagged.some((c) => c.horizon !== undefined) ? ", at each reported horizon" : " coefficients"}. Descriptive specification comparisons, not a significance test or a joint agreement test.`,
      },
    ];
  }
  const summaries = result.results.flatMap((r) =>
    records(r.sensitivity.summary).map((s) => ({ r, s })),
  );
  if (summaries.length)
    return summaries.slice(0, 1).map(({ r, s }) => {
      const range = s.estimate_range ?? s.peak_response_range;
      const n = Number(s.comparable_alternatives),
        share = Number(s.sign_agreement_share);
      const name = termLabel(
        text(s.term ?? s.variable),
        countryIndicators(manifest.indicators, r.country),
      );
      const scope = `${manifest.countries.find((c) => c.iso3 === r.country)?.name ?? r.country} · ${name}${s.sign_comparison_horizon !== undefined ? ` · sign at horizon ${text(s.sign_comparison_horizon)}; range of selected peaks` : " · coefficient"}.`;
      return {
        line: `Same sign in ${Math.round(n * share)} of ${n} alternatives${Array.isArray(range) ? ` · ${s.estimate_range ? "estimate" : "selected-peak"} range ${significant(range[0])} to ${significant(range[1])}` : ""}`,
        scope,
      };
    });
  // Evaluation returns RMSE rows, not sign-agreement or material-change flags.
  // Reproduce the h=1 ARIMA metrics already shown in its sensitivity table.
  return result.results.flatMap((r) =>
    r.sensitivity.variants.flatMap((v) => {
      const metric = records(v.metrics).find(
        (m) => m.horizon === 1 && m.model === "ARIMA",
      );
      return metric
        ? [
            {
              line: `${sensitivityDisplayLabel(v)} · ARIMA / random walk RMSE ${significant(metric.relative_rmse)}`,
              scope:
                "One quarter ahead; reported evaluation sensitivity, with no material-change classification.",
            },
          ]
        : [];
    }),
  );
}
