import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DiagnosticResults } from "../src/components/DiagnosticResults";
import { DiagnosticControls } from "../src/components/DiagnosticControls";
import { TemplateSources } from "../src/components/TemplateSources";
import { breakConfig } from "../src/diagnosticModels";
import { chartData, resultTableBlocks } from "../src/resultData";
import { tableValue } from "../src/format";
import type {
  AnalysisConfig,
  AnalysisResult,
  CountryResult,
  Manifest,
} from "../src/types";
const manifest = {
  countries: [],
  indicators: [],
  templates: [],
} as unknown as Manifest;
it("attaches the actual first-stage specification with its data variant and covariance", () => {
  const first = {
    schema_version: 1,
    countries: ["EA"],
    series: [],
    frequency: "Q",
    model: { id: "ident.external_series", params: { lags: 2 } },
    identification: { id: "recursive", params: { order: ["a", "b"] } },
    outputs: {},
  } as unknown as AnalysisConfig;
  const result = {
    config: {
      model: { id: "cmp.common_shock", params: { policy_measure: "dfr" } },
    },
    first_stage: { config: first },
  } as unknown as AnalysisResult;
  const before = JSON.stringify(result),
    c = breakConfig(result)!;
  expect(c.model.id).toBe("test.break");
  expect(c.model.params).toMatchObject({
    host: "ident.external_series",
    source_variant: "dfr",
    covariance: "HAC",
    hac_lags: 4,
    lags: 2,
  });
  expect(c.identification).toEqual(first.identification);
  expect(JSON.stringify(result)).toBe(before);
  const cards = renderToStaticMarkup(<TemplateSources config={c} />);
  expect(cards).toContain("ECB DFR");
  c.model.params.source_variant = "rate_3m";
  expect(renderToStaticMarkup(<TemplateSources config={c} />)).toContain(
    "EA 3-month rate",
  );
});
it("shows deterministic cases in words and integer ranks, with all critical levels exported", () => {
  const result = {
    country: "USA",
    status: "ok",
    model_id: "test.coint",
    actual_sample: { transforms: {} },
    sensitivity: { variants: [] },
    cointegration: {
      variables: ["a", "b"],
      deterministic_case: "Unrestricted constant (case III)",
      var_lags: 2,
      lagged_differences: 1,
      suggested_rank: 1,
      johansen: [
        {
          null_rank: 0,
          trace: 20,
          maximum_eigenvalue: 15,
          trace_critical: { 90: 13, 95: 15, 99: 19 },
          max_eigen_critical: { 90: 12, 95: 14, 99: 18 },
        },
      ],
      engle_granger: [],
    },
  } as unknown as CountryResult;
  const html = renderToStaticMarkup(
    <DiagnosticResults result={result} manifest={manifest} />,
  );
  expect(html).toContain("Unrestricted constant (case III)");
  expect(html).toContain("Trace 99%");
  expect(tableValue("Null rank", 1)).toBe("1");
  expect(chartData(result, [])[0].xAxisTitle).toBe("Null cointegration rank");
  expect(JSON.stringify(resultTableBlocks(result))).toContain("trace_critical");
});
it("keeps the new model restrictions and user-chosen rank visible", () => {
  const config = {
    model: { id: "vecm", params: {} },
    series: [{ concept_id: "x" }, { concept_id: "y" }],
    frequency: "Q",
  } as unknown as AnalysisConfig;
  const html = renderToStaticMarkup(
    <DiagnosticControls
      config={config}
      manifest={manifest}
      update={() => {}}
    />,
  );
  expect(html).toContain("User-chosen cointegration rank");
  expect(html).toContain("Only levels or log levels");
  expect(html).toContain("responses can be permanent");
  expect(html).toContain("Unrestricted constant and linear trend (case V)");
});
it("labels the break dimension, statistic scale and all four calibrations", () => {
  const result = {
    country: "EA",
    status: "ok",
    model_id: "test.break",
    actual_sample: { transforms: {} },
    sensitivity: { variants: [] },
    break_tests: {
      covariance: "HAC",
      tested_coefficients: 11,
      minimum_segment_observations: 17,
      minimum_segment_observations_per_coefficient: 17 / 11,
      hac_lags: 4,
      supremum: {
        date: "2004-Q1",
        f_statistic: 29.3,
        p_value: 0.002,
        p_value_method: "Fixed-regressor bootstrap",
      },
      critical_values: { 90: 4, 95: 5, 99: 6 },
      recursive: [],
      candidate_path: [],
      inference_variants: [
        "Conventional asymptotic",
        "HAC asymptotic",
        "HC bootstrap",
        "HAC bootstrap",
      ].map((label) => ({ label, critical_values: { 95: 5 } })),
      bootstrap: {},
      chow: {},
      tested_terms: [],
      fixed_nuisance_terms: [],
      notes: [],
    },
  } as unknown as CountryResult;
  const html = renderToStaticMarkup(
    <DiagnosticResults result={result} manifest={manifest} />,
  );
  expect(html).toContain("q = 11");
  expect(html).toContain("Minimum trimmed segment: 17 observations");
  expect(html).toContain("Wald/q");
  expect(html).toContain("499 seeded bootstrap draws");
  expect(html).toContain("HC bootstrap");
  expect(chartData(result, [])[0].unit).toContain("q = 11");
});
