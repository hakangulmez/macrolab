import { describe, expect, it } from "vitest";
import {
  chartData,
  analysisCsvRows,
  resultCsvRows,
  resultTableBlocks,
  resultUnit,
} from "../src/resultData";
import type { CountryResult, Indicator, JsonRecord } from "../src/types";
const indicators: Indicator[] = [
  {
    concept_id: "y",
    title: "Output",
    source_segments: [{ unit: "national currency", unit_mult: 6 }],
  },
  { concept_id: "x", title: "Price index", unit: "index" },
];
function result(model_id: string, extra: JsonRecord = {}): CountryResult {
  return {
    country: "USA",
    model_id,
    status: "ok",
    label: "Descriptive",
    checks: [],
    actual_sample: {
      start: "2000-Q1",
      end: "2000-Q3",
      nobs: 3,
      common_nobs: 3,
      periods: ["2000-Q1", "2000-Q2", "2000-Q3"],
      dropped_periods: [],
      frequency_conversion: {},
      transforms: {},
    },
    sensitivity: { status: "not_applicable", variants: [] },
    ...extra,
  };
}
const coefficient = {
  term: "x",
  estimate: 0.5,
  std_error: 0.1,
  lower: 0.3,
  upper: 0.7,
  p_value: 0.000000025,
};
const filtered = [
  {
    date: "2000-Q1",
    series: "y",
    value: 12,
    trend: 10,
    cycle: 2,
    fitted: 11,
    residual: 1,
  },
  {
    date: "2000-Q2",
    series: "y",
    value: 15,
    trend: 13,
    cycle: 2,
    fitted: 14,
    residual: 1,
  },
];
describe("substantive result projections", () => {
  it("preserves each sensitivity configuration hash when analysis provenance is attached to CSV rows", () => {
    const baseline = { model: { id: "var.ols", params: { lags: 2 } } };
    const alternative = { model: { id: "var.ols", params: { lags: 4 } } };
    const output = result("var.ols", {
      sensitivity: {
        status: "available",
        variants: [
          {
            variant_id: "baseline",
            config_hash: "baseline-hash",
            config: baseline,
          },
          {
            variant_id: "lags_4",
            config_hash: "alternative-hash",
            config: alternative,
          },
        ],
      },
    });
    const rows = analysisCsvRows({
      results: [output],
      snapshot_id: "reviewed-snapshot",
      config_hash: "baseline-hash",
    });
    expect(
      rows.every(
        (row) =>
          row.config_hash === "baseline-hash" &&
          row.snapshot === "reviewed-snapshot",
      ),
    ).toBe(true);
    expect(rows.find((row) => row.variant_id === "baseline")).toMatchObject({
      record_type: "sensitivity_variant",
      variant_config_hash: "baseline-hash",
      config: baseline,
    });
    expect(rows.find((row) => row.variant_id === "lags_4")).toMatchObject({
      record_type: "sensitivity_variant",
      variant_config_hash: "alternative-hash",
      config: alternative,
    });
  });
  it.each(["filter.hp", "filter.hamilton"])(
    "preserves observed, trend and cycle for %s",
    (id) => {
      const output = result(id, { filtered_series: filtered });
      const charts = chartData(output, indicators);
      expect(charts).toHaveLength(2);
      expect(charts[0].points[0]).toMatchObject({ value: 12, comparison: 10 });
      expect(charts[1].points.map((p) => p.value)).toEqual([2, 2]);
      expect(charts[0].unit).toBe("national currency ×10^6");
      expect(resultTableBlocks(output)[0].columns).toEqual(
        expect.arrayContaining(["value", "trend", "cycle"]),
      );
      expect(
        resultCsvRows(output).find((r) => r.date === "2000-Q1"),
      ).toMatchObject({ value: 12, trend: 10, cycle: 2 });
    },
  );
  it("ARDL displays fitted-only rows, residuals, coefficients and its ECM reparameterisation", () => {
    const output = result("sing.ardl", {
      coefficients_table: [coefficient],
      error_correction_table: [
        { ...coefficient, term: "y.L1", estimate: -0.4 },
      ],
      filtered_series: filtered.map(({ date, series, fitted, residual }) => ({
        date,
        series,
        fitted,
        residual,
      })),
    });
    const charts = chartData(output, indicators);
    expect(
      charts.find((c) => c.name === "Output: fitted")?.points[0].value,
    ).toBe(11);
    expect(
      charts.find((c) => c.name === "Output: residual")?.points[0].value,
    ).toBe(1);
    expect(
      resultTableBlocks(output).find((b) =>
        b.title.startsWith("ARDL error-correction"),
      )?.rows[0].estimate,
    ).toBe(-0.4);
    expect(
      resultCsvRows(output).some(
        (r) => r.term === "y.L1" && r.estimate === -0.4,
      ),
    ).toBe(true);
  });
  it("OLS distinguishes observed/fitted outcomes and keeps small p-values numerically", () => {
    const output = result("sing.ols", {
      coefficients_table: [coefficient],
      filtered_series: filtered,
    });
    expect(
      chartData(output, indicators).find((c) =>
        c.name.includes("observed and fitted"),
      )?.points[0],
    ).toMatchObject({ value: 12, comparison: 11 });
    expect(resultCsvRows(output).find((r) => r.term === "x")?.p_value).toBe(
      2.5e-8,
    );
  });
  it("rolling correlations keep each pair and constant-window null gaps", () => {
    const output = result("desc.corr", {
      test_results: [
        {
          series_a: "x",
          series_b: "y",
          statistic: 0.2,
          test: "Pearson correlation",
        },
      ],
      filtered_series: [
        {
          date: "2000-Q1",
          series_a: "x",
          series_b: "y",
          value: 0.3,
          window: 3,
        },
        {
          date: "2000-Q2",
          series_a: "x",
          series_b: "y",
          value: null,
          window: 3,
        },
        {
          date: "2000-Q3",
          series_a: "x",
          series_b: "y",
          value: 0.5,
          window: 3,
        },
        {
          date: "2000-Q1",
          series_a: "x",
          series_b: "z",
          value: -0.3,
          window: 3,
        },
      ],
    });
    const charts = chartData(output, indicators);
    expect(charts).toHaveLength(2);
    expect(charts[0].points.map((p) => p.value)).toEqual([0.3, null, 0.5]);
    expect(charts[1].name).toContain("x / z");
    expect(charts[0].unit).toContain("correlation");
    expect(
      resultCsvRows(output).find((r) => r.date === "2000-Q2")?.value,
    ).toBeNull();
    expect(
      resultCsvRows(output).find((r) => r.statistic === 0.2),
    ).toMatchObject({ series_a: "x", series_b: "y" });
  });
  it("Granger retains direction, p-value, degrees of freedom and the ninth-column null", () => {
    const row = {
      test: "Granger SSR F",
      dependent: "y",
      regressor: "x",
      lags: 4,
      statistic: 3.2,
      p_value: 0.025,
      df_denominator: 82,
      df_numerator: 4,
      null: "Lagged regressor coefficients are jointly zero.",
    };
    const output = result("test.granger", { test_results: [row] });
    expect(chartData(output, indicators)[0].points[0].period).toBe(
      "x → y (4 lags)",
    );
    expect(resultTableBlocks(output)[0].columns).toContain("null");
    expect(
      resultCsvRows(output).find((r) => r.test === row.test),
    ).toMatchObject(row);
  });
  it("unit-root tables retain critical values, censoring and each effective test sample", () => {
    const output = result("test.adf_kpss_pp", {
      test_results: [
        {
          series: "y",
          test: "KPSS",
          null: "stationarity",
          trend: "c",
          statistic: 0.01,
          p_value: 0.1,
          lags: 4,
          nobs: 3,
          critical_values: { "5%": 0.463 },
          p_value_censored: true,
          sample: { start: "2000-Q1", end: "2000-Q3", nobs: 3 },
        },
        {
          series: "y",
          test: "ADF",
          null: "unit root",
          statistic: -2,
          p_value: 0.05,
          nobs: 2,
          sample: { start: "2000-Q2", end: "2000-Q3", nobs: 2 },
        },
      ],
    });
    const table = resultTableBlocks(output)[0];
    expect(table.columns).toEqual(
      expect.arrayContaining([
        "critical_values",
        "p_value_censored",
        "sample_start",
        "sample_end",
        "sample_nobs",
      ]),
    );
    expect(table.rows[1].sample_start).toBe("2000-Q2");
    expect(chartData(output, indicators).map((c) => c.name)).toEqual([
      "KPSS",
      "ADF",
    ]);
  });
  it("country plot lines never splice countries, and rankings label country bars", () => {
    const plot = result("desc.plot", {
      filtered_series: [
        { country: "USA", series: "y", date: "2000-Q1", value: 2 },
        { country: "GBR", series: "y", date: "2000-Q1", value: 8 },
      ],
    });
    expect(chartData(plot, indicators).map((c) => c.name)).toEqual([
      "USA · Output",
    ]);
    expect(chartData(plot, indicators).map((c) => c.points[0].value)).toEqual([
      2,
    ]);
    expect(
      chartData({ ...plot, country: "GBR" }, indicators)[0].points[0].value,
    ).toBe(8);
    const comparison = result("desc.compare", {
      test_results: [
        { country: "USA", series: "y", statistic: 2, method: "mean", rank: 2 },
        { country: "GBR", series: "y", statistic: 8, method: "mean", rank: 1 },
      ],
    });
    expect(
      chartData(comparison, indicators)[0].points.map((p) => p.period),
    ).toEqual(["USA", "GBR"]);
    expect(resultTableBlocks(comparison)[0].title).toContain("rankings");
    expect(resultCsvRows(comparison).find((r) => r.rank === 1)?.country).toBe(
      "GBR",
    );
  });
  it("rolling coefficient intervals and exact window samples remain available", () => {
    const output = result("sing.rolling", {
      coefficients_table: [coefficient],
      filtered_series: [
        { ...coefficient, date: "2000-Q3", window_start: "2000-Q1", nobs: 3 },
      ],
      diagnostics: {
        coefficient_sample: { start: "2000-Q1", end: "2000-Q3", nobs: 3 },
      },
    });
    expect(chartData(output, indicators)[0].points[0]).toMatchObject({
      value: 0.5,
      lower: 0.3,
      upper: 0.7,
    });
    expect(
      resultTableBlocks(output).find((b) => b.title.includes("exact window"))
        ?.rows[0].window_start,
    ).toBe("2000-Q1");
    expect(
      resultCsvRows(output).some((r) => r.window_start === "2000-Q1"),
    ).toBe(true);
  });
  it("unidentified VAR separates equation coefficients and preserves diagnostic tests", () => {
    const output = result("var.ols", {
      coefficients_table: [
        { ...coefficient, equation: "y" },
        { ...coefficient, equation: "x", estimate: -0.25 },
      ],
      diagnostics: {
        normality: { statistic: 8, pvalue: 0.02 },
        residual_whiteness: { unavailable: "Too few observations" },
      },
    });
    expect(chartData(output, indicators).map((c) => c.name)).toEqual([
      "y: equation coefficients",
      "x: equation coefficients",
    ]);
    expect(
      resultTableBlocks(output).find((b) => b.title === "Diagnostic tests")
        ?.rows[1].unavailable,
    ).toBe("Too few observations");
  });
  it("identified VAR keeps response bands and FEVD shares, with transformation-aware units", () => {
    const output = result("ident.recursive", {
      irf: {
        periods: [0, 1],
        variables: ["y", "x"],
        values: [
          [0, 0.25],
          [0.2, 0.1],
        ],
        lower: [
          [0, 0.25],
          [-0.1, 0.02],
        ],
        upper: [
          [0, 0.25],
          [0.5, 0.18],
        ],
        shock: "x",
        shock_size: 0.25,
        band_level: 0.68,
        band_method: "bootstrap",
      },
      fevd: {
        periods: [1],
        variables: ["y", "x"],
        shocks: ["y", "x"],
        values: [
          [
            [0.8, 0.2],
            [0.3, 0.7],
          ],
        ],
      },
    });
    output.actual_sample.transforms = {
      y: { transform: "qoq_saar" },
      x: { transform: "log" },
    };
    expect(chartData(output, indicators).map((c) => c.unit)).toEqual([
      "percentage points",
      "log points",
    ]);
    expect(chartData(output, indicators)[0].points[1]).toMatchObject({
      lower: -0.1,
      upper: 0.5,
    });
    expect(
      resultCsvRows(output).find(
        (r) => r.response === "y" && r.shock === "x" && r.share !== undefined,
      )?.share,
    ).toBe(0.2);
    expect(resultUnit(output, "unemp", indicators, true)).toBe(
      "percentage points",
    );
  });
  it("never draws an all-missing curve or mutates original results", () => {
    const output = result("desc.corr", {
      filtered_series: [
        {
          date: "2000-Q1",
          series_a: "a",
          series_b: "b",
          value: null,
          window: 3,
        },
      ],
    });
    const before = structuredClone(output);
    expect(chartData(output, indicators)).toEqual([]);
    resultTableBlocks(output);
    resultCsvRows(output);
    expect(output).toEqual(before);
  });
});
