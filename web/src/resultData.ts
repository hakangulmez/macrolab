/** Pure projections of the twelve v0 output contracts; no statistical calculations. */
import { countryIndicators } from "./displayLabels";
import type { AxisScale } from "./chartScale";
import type { ChartPoint } from "./components/Chart";
import { number, significant, record, records, text, title } from "./format";
import type {
  AnalysisConfig,
  AnalysisResult,
  CountryResult,
  Indicator,
  IRF,
  JsonRecord,
} from "./types";

export interface ResultChart {
  variable?: string;
  name: string;
  unit: string;
  points: ChartPoint[];
  summary: string;
  bar?: boolean;
  coefficient?: boolean;
  transformation?: string;
  axis?: AxisScale;
  intervalLabel?: string;
  pngNote?: string;
  pngComparisonLabel?: string;
}
export interface ResultTableBlock {
  title: string;
  rows: JsonRecord[];
  columns?: string[];
}
const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const optional = (value: unknown): number | undefined =>
  finite(value) ?? undefined;
const columns = (rows: JsonRecord[]) => [...new Set(rows.flatMap(Object.keys))];
const group = (rows: JsonRecord[], key: (row: JsonRecord) => string) => {
  const groups = new Map<string, JsonRecord[]>();
  for (const row of rows) {
    const id = key(row);
    groups.set(id, [...(groups.get(id) ?? []), row]);
  }
  return [...groups];
};

/** A response changes a percent-valued series in percentage points. */
export function resultUnit(
  result: CountryResult,
  concept: string,
  indicators: Indicator[],
  response = false,
): string {
  const transform = record(result.actual_sample.transforms[concept]);
  const kind = text(transform.transform, "level");
  if (["qoq_saar", "yoy_pct", "log_diff"].includes(kind))
    return response
      ? "percentage points"
      : kind === "qoq_saar"
        ? "% growth, annualised"
        : "% growth";
  if (kind === "log") return "log points";
  if (kind === "index_to_base")
    return response ? "index points" : "index (base = 100)";
  if (
    ["hp_cycle", "hamilton_cycle"].includes(kind) &&
    record(transform.params).log === true
  )
    return "100 × log deviation";
  const indicator = indicators.find((i) => i.concept_id === concept);
  const segments = records(indicator?.source_segments);
  const units = [
    ...new Set(
      segments.map((s) => text(s.unit_label ?? s.unit, "")).filter(Boolean),
    ),
  ];
  const unit = text(
    indicator?.unit_label ?? indicator?.unit,
    units.length === 1 ? units[0] : "",
  );
  const percent =
    /percent|percentage|pct|%/i.test(unit) ||
    ["policy_rate", "unemp", "credit_pnfs"].includes(concept) ||
    /%/.test(indicator?.title ?? "");
  if (percent)
    return response || ["diff", "yoy_diff"].includes(kind)
      ? "percentage points"
      : unit || "%";
  const multipliers = [
    ...new Set(
      segments.map((s) => s.unit_mult).filter((v) => typeof v === "number"),
    ),
  ];
  const multiplier =
    indicator?.unit_mult ??
    (multipliers.length === 1 ? multipliers[0] : undefined);
  if (multipliers.length > 1 || units.length > 1)
    return "mixed source units (see catalogue)";
  return unit
    ? `${unit}${typeof multiplier === "number" && multiplier !== 0 ? ` ×10^${multiplier}` : ""}`
    : "source units (see catalogue)";
}
function projection(result: CountryResult, concept: string): JsonRecord {
  return record(
    record(record(result.response_results)[concept]).local_projection ??
      result.local_projection,
  );
}
function transformLabel(result: CountryResult, concept: string): string {
  const lp = projection(result, concept);
  if (lp.response_definition)
    return (
      String(lp.response_definition) +
      (lp.response_mode === "growth_log" && Number(lp.growth_scale) > 1
        ? " · annualised"
        : "")
    );
  const spec = record(result.actual_sample.transforms[concept]);
  const kind = text(spec.transform, "level");
  const labels: Record<string, string> = {
    qoq_saar: "quarter-on-quarter annualised growth",
    yoy_pct: "year-on-year percentage growth",
    yoy_diff: "year-on-year change",
    log_diff: "log change (%)",
    diff: "period-to-period change",
    log: "log level",
    level: "level",
  };
  if (kind === "hp_cycle")
    return record(spec.params).log === true
      ? "HP gap (100 × log deviation)"
      : "HP cycle";
  return labels[kind] ?? kind.replaceAll("_", " ");
}

export function termLabel(term: string, indicators: Indicator[]): string {
  let label = term === "const" ? "Intercept" : term;
  for (const indicator of [...indicators].sort(
    (a, b) => b.concept_id.length - a.concept_id.length,
  )) {
    label = label.replaceAll(indicator.concept_id, indicator.title);
  }
  return label
    .replace(/^L(\d+)\./, "Lag $1 · ")
    .replace(/^trend$/, "Time trend")
    .replace(/^(.*)\.L(\d+)$/, "$1 (lag $2)")
    .replaceAll("_", " ");
}

export function coefficientInterval(
  result: Pick<CountryResult, "diagnostics" | "coefficients_table">,
): string {
  const rows = records(result.coefficients_table);
  const level = Number(
    rows[0]?.confidence_level ?? record(result.diagnostics).confidence ?? 0.95,
  );
  const covariance = text(
    rows[0]?.covariance ?? record(result.diagnostics).covariance,
    "OLS",
  );
  return `${Math.round(level * 100)}% confidence interval (${covariance})`;
}

function coefficientCharts(
  result: CountryResult,
  indicators: Indicator[],
): ResultChart[] {
  return group(records(result.coefficients_table), (r) =>
    text(r.equation, ""),
  ).map(([equation, rows]) => ({
    name: equation
      ? `${termLabel(equation, indicators)}: equation coefficients`
      : "Estimated coefficients",
    unit: "coefficient units vary by term",
    coefficient: true,
    intervalLabel: coefficientInterval(result),
    points: rows
      .filter((r) => r.term !== "const")
      .map((r) => ({
        period: (() => {
          const term = text(r.term);
          const indicator = [...indicators]
            .sort((a, b) => b.concept_id.length - a.concept_id.length)
            .find(
              (i) =>
                term === i.concept_id ||
                term.endsWith(`.${i.concept_id}`) ||
                term.startsWith(`${i.concept_id}.`),
            );
          return `${termLabel(term, indicators)}${indicator ? ` · ${transformLabel(result, indicator.concept_id)}` : ""}`;
        })(),
        value: finite(r.estimate),
        lower: optional(r.lower),
        upper: optional(r.upper),
      })),
    summary: `${coefficientInterval(result)}; magnitudes across different regressor units are not directly comparable. Intercept and full numerical results are in the table.`,
  }));
}

export function chartData(
  result: CountryResult,
  indicators: Indicator[],
): ResultChart[] {
  if (result.status !== "ok") return [];
  indicators = countryIndicators(indicators, result.country);
  let charts: ResultChart[] = [];
  if (result.irf) {
    const irf = result.irf;
    charts = irf.variables.map((variable, j) => {
      const points = irf.periods.map((h, i) => ({
        period: h,
        value: irf.values[i][j],
        lower: irf.lower[i][j],
        upper: irf.upper[i][j],
      }));
      const peak = points.reduce((a, b) =>
        Math.abs(b.value) > Math.abs(a.value) ? b : a,
      );
      return {
        variable,
        name: title(variable, indicators),
        transformation: transformLabel(result, variable),
        unit: ["cumulative_log", "growth_log"].includes(
          String(projection(result, variable).response_mode),
        )
          ? String(projection(result, variable).response_definition)
          : resultUnit(result, variable, indicators, true),
        points,
        summary: `Largest absolute response: ${number(peak.value, 3)} at horizon ${peak.period}; ${Math.round(irf.band_level * 100)}% pointwise band ${peak.lower > 0 || peak.upper < 0 ? "excludes" : "includes"} zero there.`,
      };
    });
    const pass = record(result.pass_through);
    if (pass.status === "ok") {
      charts[0].summary = text(pass.secondary_label) + ". " + charts[0].summary;
      charts[0].name = "CPI response (secondary)";
      charts.unshift({
        name: "Cumulative pass-through ratio",
        unit: "% CPI per 1% cumulative depreciation",
        points: records(pass.horizons).map((r) => ({
          period: Number(r.horizon),
          value: finite(r.ratio),
          lower: optional(record(record(r.bands)["0.68"]).lower),
          upper: optional(record(record(r.bands)["0.68"]).upper),
        })),
        summary:
          text(pass.sign_convention) +
          " " +
          text(pass.interval_method) +
          "; 68% shown.",
      });
      charts.push({
        name: `${text(pass.exchange_rate).toUpperCase()} cumulative response`,
        unit: "cumulative % change in the level",
        points: records(pass.horizons).map((r) => ({
          period: Number(r.horizon),
          value: finite(r.fx_cumulative),
          // Same normal 68% interval and joint HC1/HAC marginal SE as the ratio fit.
          lower:
            Number(r.fx_cumulative) -
            0.994457883209753 * Number(r.fx_std_error),
          upper:
            Number(r.fx_cumulative) +
            0.994457883209753 * Number(r.fx_std_error),
        })),
        summary:
          "Exchange rate's subsequent path after the same initial impulse, with a 68% pointwise band; negative NEER means depreciation.",
      });
    }
  } else if (result.model_id === "desc.corr") {
    charts = group(
      records(result.filtered_series),
      (r) => `${text(r.series_a)} / ${text(r.series_b)}`,
    ).map(([pair, rows]) => ({
      name: `Rolling correlation: ${pair}`,
      unit: "correlation (−1 to 1)",
      points: rows.map((r) => ({
        period: text(r.date),
        value: finite(r.value),
      })),
      summary: `${text(rows[0]?.window)}-period trailing correlation. Missing constant-window values remain gaps; no confidence intervals or causal interpretation.`,
    }));
  } else if (result.model_id === "desc.compare") {
    charts = group(records(result.test_results), (r) => text(r.series)).map(
      ([series, rows]) => ({
        name: `${title(series, indicators)}: country ${text(rows[0]?.method, "comparison")}`,
        unit: resultUnit(result, series, indicators),
        bar: true,
        points: rows.map((r) => ({
          period: text(r.country),
          value: finite(r.statistic),
        })),
        summary:
          "Descriptive country values, not hypothesis-test statistics. Country samples and descending ranks are in the table; no confidence intervals.",
      }),
    );
  } else if (["test.adf_kpss_pp", "test.granger"].includes(result.model_id)) {
    charts = group(records(result.test_results), (r) => text(r.test)).map(
      ([test, rows]) => ({
        name: test,
        unit: "test statistic",
        bar: true,
        points: rows.map((r) => ({
          period: r.dependent
            ? `${text(r.regressor)} → ${text(r.dependent)} (${text(r.lags)} lags)`
            : text(r.series),
          value: finite(r.statistic),
        })),
        summary: `${text(rows[0]?.null, "Read the stated null hypothesis.")} Test p-values, lag choices and effective samples are in the table. No confidence interval is attached to this statistic.`,
      }),
    );
  } else {
    if (
      ["sing.ols", "sing.ardl", "var.ols", "ident.recursive"].includes(
        result.model_id,
      )
    )
      charts.push(...coefficientCharts(result, indicators));
    const filtered = records(result.filtered_series).filter(
      (r) =>
        result.model_id !== "desc.plot" ||
        r.country === undefined ||
        r.country === result.country,
    );
    const groups = group(filtered, (r) =>
      JSON.stringify([r.country ?? result.country, r.series ?? r.term]),
    );
    for (const [, rows] of groups) {
      const series = text(rows[0]?.series ?? rows[0]?.term);
      const prefix = rows[0]?.country ? `${text(rows[0].country)} · ` : "";
      const name = `${prefix}${title(series, indicators)}`;
      const unit = resultUnit(result, series, indicators);
      const points = (field: string): ChartPoint[] =>
        rows.map((r) => ({ period: text(r.date), value: finite(r[field]) }));
      if (["filter.hp", "filter.hamilton"].includes(result.model_id)) {
        charts.push(
          {
            name: `${name}: observed and trend`,
            unit,
            points: points("value").map((p, i) => ({
              ...p,
              comparison: finite(rows[i].trend),
            })),
            summary:
              "Solid: observed transformed series. Dashed comparison: fitted trend. Retrospective decomposition; no confidence interval.",
          },
          {
            name: `${name}: cycle`,
            unit,
            points: points("cycle"),
            summary:
              "Observed value minus fitted trend, in the same transformed units. No confidence interval.",
          },
        );
      } else if (["sing.ols", "sing.ardl"].includes(result.model_id)) {
        const observed = rows.some((r) => finite(r.value) !== null);
        charts.push(
          {
            name: `${name}: ${observed ? "observed and fitted" : "fitted"}`,
            unit,
            points: points(observed ? "value" : "fitted").map((p, i) =>
              observed ? { ...p, comparison: finite(rows[i].fitted) } : p,
            ),
            summary: observed
              ? "Solid: observed outcome. Dashed comparison: fitted outcome. Coefficient intervals are not prediction bands."
              : "Fitted outcome over the effective estimation sample; no prediction bands are reported.",
          },
          {
            name: `${name}: residual`,
            unit,
            points: points("residual"),
            summary:
              "Observed minus fitted outcome over the effective estimation sample.",
          },
        );
      } else if (result.model_id === "sing.rolling") {
        charts.push({
          name: `${name}: coefficient path`,
          unit: "coefficient",
          points: rows.map((r) => ({
            period: text(r.date),
            value: finite(r.estimate),
            lower: optional(r.lower),
            upper: optional(r.upper),
          })),
          summary:
            "Each point uses the window ending on that date. Intervals are pointwise; exact window starts and observation counts are retained in the table.",
        });
      } else {
        charts.push({
          name,
          unit,
          points: points("value"),
          summary:
            "Observed transformed values with explicit country and dates. No confidence interval.",
        });
      }
    }
  }
  return charts.filter((chart) => chart.points.some((p) => p.value !== null));
}

function irfRows(result: CountryResult): JsonRecord[] {
  const irf = result.irf;
  if (!irf) return [];
  return irf.periods.flatMap((h, i) =>
    irf.variables.map((variable, j) => ({
      horizon: h,
      response: variable,
      estimate: irf.values[i][j],
      lower: irf.lower[i][j],
      upper: irf.upper[i][j],
      band_level: irf.band_level,
      band_method: irf.band_method,
      shock: irf.shock,
      shock_size: irf.shock_size,
    })),
  );
}
function fevdRows(result: CountryResult): JsonRecord[] {
  const f = record(result.fevd);
  const values = (f.values ?? []) as number[][][];
  return values.flatMap((h, i) =>
    h.flatMap((v, j) =>
      v.map((share, k) => ({
        horizon: (f.periods as number[])[i],
        response: (f.variables as string[])[j],
        shock: (f.shocks as string[])[k],
        share,
      })),
    ),
  );
}
function completeRows(rows: JsonRecord[]): JsonRecord[] {
  return rows.map((row) => {
    const sample = record(row.sample);
    return Object.keys(sample).length
      ? {
          ...row,
          sample_start: sample.start,
          sample_end: sample.end,
          sample_nobs: sample.nobs,
        }
      : { ...row };
  });
}
export function resultTableBlocks(result: CountryResult): ResultTableBlock[] {
  const blocks: ResultTableBlock[] = [];
  const add = (name: string, rows: JsonRecord[]) => {
    if (rows.length) {
      const complete = completeRows(rows);
      blocks.push({ title: name, rows: complete, columns: columns(complete) });
    }
  };
  add(
    result.model_id === "sing.rolling"
      ? "Last-window coefficients and intervals"
      : "Coefficients and intervals",
    records(result.coefficients_table),
  );
  add(
    "ARDL error-correction coefficients (reparameterisation, not a cointegration test)",
    records(result.error_correction_table),
  );
  const names: Record<string, string> = {
    "desc.plot": "Observed transformed data by country",
    "desc.corr": "Rolling correlations by series pair",
    "sing.ols": "Observed, fitted and residual series",
    "sing.ardl": "Fitted and residual series",
    "sing.rolling": "Coefficient paths and exact window samples",
    "filter.hp": "HP observed, trend and cycle values",
    "filter.hamilton": "Hamilton observed, trend and cycle values",
  };
  add(
    names[result.model_id] ?? "Reported series",
    records(result.filtered_series),
  );
  add(
    result.model_id === "desc.compare"
      ? "Country comparison and rankings"
      : result.model_id === "desc.corr"
        ? "Full-sample correlations"
        : "Tests, null hypotheses and effective samples",
    records(result.test_results),
  );
  add("Impulse responses and pointwise intervals", irfRows(result));
  const diagnostics = record(result.diagnostics);
  add(
    "Diagnostic tests",
    ["normality", "residual_whiteness"]
      .filter((key) => diagnostics[key] !== undefined)
      .map((key) => ({ test: key, ...record(diagnostics[key]) })),
  );
  add(
    "Final coefficient estimation sample",
    Object.keys(record(diagnostics.coefficient_sample)).length
      ? [record(diagnostics.coefficient_sample)]
      : [],
  );
  if (result.irf) {
    add("Shock normalization", [
      {
        ...record(result.irf.shock_normalization),
        normalization: result.irf.normalization,
        band_interpretation: result.irf.band_interpretation,
      },
    ]);
  }
  return blocks;
}

/** Tagged rows allow one CSV to retain tests, paths, decompositions and metadata. */
export function resultCsvRows(result: CountryResult): JsonRecord[] {
  const sample = result.actual_sample;
  const base = {
    country: result.country,
    model: result.model_id,
    status: result.status,
    actual_sample_start: sample.start,
    actual_sample_end: sample.end,
    actual_sample_nobs: sample.nobs,
    common_nobs: sample.common_nobs,
  };
  const output: JsonRecord[] = [
    { ...base, record_type: "actual_sample", ...sample },
  ];
  if (result.pass_through) {
    const pass = record(result.pass_through);
    const metadata = { ...pass };
    delete metadata.horizons;
    output.push({
      ...base,
      record_type: "Pass-through definition",
      ...metadata,
    });
    for (const row of records(pass.horizons))
      output.push({
        ...base,
        record_type: "Cumulative pass-through ratio",
        ...row,
      });
  }
  for (const block of resultTableBlocks(result))
    for (const row of block.rows)
      output.push({ ...base, record_type: block.title, ...row });
  for (const row of fevdRows(result))
    output.push({
      ...base,
      record_type: "Forecast-error variance shares (0–1)",
      ...row,
    });
  output.push({
    ...base,
    record_type: "diagnostics",
    ...record(result.diagnostics),
  });
  for (const variant of result.sensitivity.variants)
    output.push({
      ...base,
      record_type: "sensitivity_variant",
      ...variant,
      variant_config_hash: variant.config_hash,
    });
  for (const row of result.sensitivity.summary ?? [])
    output.push({ ...base, record_type: "sensitivity_summary", ...row });
  output.push({
    ...base,
    record_type: "sensitivity_definition",
    comparison_rule: result.sensitivity.comparison_rule,
    limitations: result.sensitivity.limitations,
    lag_criteria: record(result.sensitivity).lag_criteria,
  });
  for (const check of result.checks)
    output.push({ ...base, record_type: "check", ...check });
  result.notes?.forEach((note) =>
    output.push({ ...base, record_type: "note", note }),
  );
  return output;
}

/** Keep analysis-level provenance separate from each sensitivity configuration. */
export function analysisCsvRows(
  result: Pick<AnalysisResult, "results" | "snapshot_id" | "config_hash"> &
    Partial<Pick<AnalysisResult, "checks">>,
): JsonRecord[] {
  const rows = result.results.flatMap((item) =>
    resultCsvRows(item).map((row) => ({
      ...row,
      snapshot: result.snapshot_id,
      config_hash: result.config_hash,
    })),
  );
  // Multi-response analyses also carry checks outside the first response's
  // country record. Export those instances verbatim, never the display groups.
  return [
    ...rows,
    ...(result.checks ?? []).map((check) => ({
      record_type: "analysis_check",
      ...check,
      snapshot: result.snapshot_id,
      config_hash: result.config_hash,
    })),
  ];
}

export const selectedPeakFootnote =
  "Selected-peak comparisons are descriptive. Pointwise intervals do not provide simultaneous coverage across horizons.";

export function specificationLabel(variant: JsonRecord): string {
  if (typeof variant.label === "string" && variant.label) return variant.label;
  const id = text(variant.variant_id, "Comparison");
  const labels: Record<string, string> = {
    baseline: "Baseline",
    extended_var: "Extended VAR · exchange rate and credit",
    reverse_order: "Reversed recursive order",
    rotate_order: "Rotated recursive order",
    lag_aic: "AIC-selected lag",
    lag_bic: "BIC-selected lag",
    lag_hqic: "HQIC-selected lag",
    covid_include: "Include COVID quarters",
    end_2019: "End sample in 2019",
    full_sample: "Full sample",
    recent_half_full_sample: "Recent half of full sample",
    quarterly_okun: "Quarterly Okun specification",
  };
  return (
    labels[id] ??
    (/^lags_\d+$/.test(id) ? `${id.slice(5)} lags` : id.replaceAll("_", " "))
  );
}

export function shockHeading(
  irf: IRF,
  config: AnalysisConfig,
  indicators: Indicator[],
): string {
  if (config.model.params.template_id === "tur_pass_through")
    return "Türkiye: cumulative pass-through ratio";
  const policy = ["policy_rate", "us_policy_rate"].includes(irf.shock);
  const amount = `${irf.shock_size > 0 ? "+" : ""}${number(irf.shock_size, 2)}`;
  const mode =
    (config.outputs.irf?.shock_mode ??
      (config.model.params.first_stage as AnalysisConfig | undefined)?.outputs
        .irf?.shock_mode) === "one_sd"
      ? " (one standard deviation)"
      : "";
  return `${policy ? "Policy-rate" : title(irf.shock, indicators)} shock: ${amount} ${policy ? "pp" : "transformed units"}${mode}`;
}

/** Display summaries use reported output and notes; they never reinterpret significance. */
export function readingBullets(
  result: CountryResult,
  indicators: Indicator[],
): string[] {
  const charts = chartData(result, indicators);
  const v1 =
    result.model_id === "lp.ols" || result.model_id === "cmp.common_shock";
  const bullets = [
    v1
      ? result.label
      : result.irf
        ? "A conditional model scenario: responses depend on the recursive ordering and included variables."
        : "These estimates describe association in the actual sample; they do not establish causation.",
  ];
  const responses = result.irf
    ? charts.filter((_, i) => result.irf?.variables[i] !== result.irf?.shock)
    : charts;
  bullets.push(
    ...responses.slice(0, 2).map((chart) => `${chart.name}: ${chart.summary}`),
  );
  const notes = result.notes ?? [];
  const output = notes.some((note) =>
    note.startsWith("The estimated output response rises after the tightening"),
  );
  const price = notes.some((note) =>
    note.startsWith("The estimated price response rises after the tightening"),
  );
  const tightening =
    result.irf &&
    ["policy_rate", "us_policy_rate"].includes(result.irf.shock) &&
    result.irf.shock_size > 0;
  const v1Puzzle = notes.find((note) =>
    note.startsWith("An output/price puzzle appears"),
  );
  if (v1Puzzle) bullets.push(v1Puzzle);
  if (tightening && (output || price))
    bullets.push(
      `${output && price ? "Output and prices rise" : output ? "Output rises" : "Prices rise"} at some horizons after tightening. This output/price puzzle can reflect omitted information, ordering or sample choices; it is not evidence that tightening reliably raises activity or prices.`,
    );
  bullets.push(
    result.sensitivity.summary?.length
      ? "Agreement across the displayed specifications is sensitivity evidence, not proof that the model or identification is valid."
      : "Read the method assumptions and effective samples before interpreting magnitudes or tests.",
  );
  if (bullets.length < 3)
    bullets.splice(
      1,
      0,
      `Actual sample: ${result.actual_sample.start ?? "unavailable"} to ${result.actual_sample.end ?? "unavailable"}, ${result.actual_sample.nobs} observations.`,
    );
  return bullets.slice(0, 5);
}

const yesNo = (value: unknown): string =>
  value === true ? "Yes" : value === false ? "No" : "Not reported";
const displayRange = (value: unknown): string =>
  Array.isArray(value) && value.length === 2
    ? value.map((item) => significant(item)).join(" to ")
    : "Not reported";
const displayAgreement = (row: JsonRecord): string => {
  const share = row.sign_agreement_share;
  return typeof share === "number" && Number.isFinite(share)
    ? `${number(share * 100, 0)}% (${text(row.comparable_alternatives)} alternatives)`
    : "Not reported";
};
export function sensitivityRows(
  result: CountryResult,
  indicators: Indicator[],
): JsonRecord[] {
  return (result.sensitivity.summary ?? []).map((row) =>
    result.irf
      ? {
          Response: title(text(row.variable), indicators),
          "Baseline peak": significant(row.baseline_peak_response),
          "Peak horizon": row.baseline_peak_horizon,
          "Signed peak range": displayRange(row.peak_response_range),
          "Peak horizon range": Array.isArray(row.peak_horizon_range)
            ? row.peak_horizon_range.join(" to ")
            : "Not reported",
          "Same sign at baseline peak": displayAgreement(row),
          "Baseline band excludes zero": yesNo(
            row.baseline_band_excludes_zero_at_peak,
          ),
        }
      : {
          Term: text(row.term),
          "Baseline estimate": significant(row.baseline_estimate),
          "Estimate range": displayRange(row.estimate_range),
          "Same sign": displayAgreement(row),
          "Baseline interval excludes zero": yesNo(
            row.baseline_interval_excludes_zero,
          ),
        },
  );
}

export function mobileSummaryLines(result: AnalysisResult): string[] {
  const first =
    result.results.find((item) => item.status === "ok") ?? result.results[0];
  const irf = first?.irf;
  const sample = first?.actual_sample;
  return [
    irf
      ? `${irf.shock_size > 0 ? "+" : ""}${number(irf.shock_size, 2)} ${["policy_rate", "us_policy_rate"].includes(irf.shock) ? "pp policy shock" : "shock units"}${result.config.outputs.irf?.shock_mode === "one_sd" ? " · 1 SD" : ""}`
      : result.config.model.id,
    sample
      ? `${first.country}: ${sample.start ?? "Unavailable"}–${sample.end ?? "—"} · n = ${sample.nobs}`
      : "No estimation sample",
    irf
      ? `Model scenario · ${number(irf.band_level * 100, 0)}% pointwise intervals`
      : result.label,
  ];
}
