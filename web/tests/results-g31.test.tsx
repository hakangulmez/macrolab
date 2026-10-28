import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Results, ResultsCountry } from "../src/components/Results";
import {
  chartData,
  mobileSummaryLines,
  readingBullets,
  resultCsvRows,
  sensitivityRows,
  shockHeading,
  specificationLabel,
} from "../src/resultData";
import type {
  AnalysisConfig,
  AnalysisResult,
  CountryResult,
  Manifest,
} from "../src/types";

vi.mock("../src/components/Chart", () => ({
  Chart: ({
    title,
    summary,
    first,
  }: {
    title: string;
    summary: string;
    first: boolean;
  }) => (
    <figure data-testid="result-chart" data-export-owner={first}>
      <figcaption>{title}</figcaption>
      <p>{summary}</p>
    </figure>
  ),
}));
const config: AnalysisConfig = {
  schema_version: 1,
  snapshot_id: "fixture",
  countries: ["USA"],
  series: [{ concept_id: "policy_rate", role: "shock", transform: "level" }],
  frequency: "Q",
  aggregation: {},
  sample: { start: "1999-Q1", end: "2025-Q3" },
  special_periods: { covid: "dummies" },
  model: { id: "var.ols", params: {} },
  identification: null,
  outputs: {
    irf: {
      horizon: 2,
      bands: 0.68,
      shock_size: 1,
      method: "bootstrap",
      draws: 200,
      shock_mode: "one_sd",
    },
  },
  comparison: {},
  seed: 42,
};
const country: CountryResult = {
  country: "USA",
  model_id: "var.ols",
  status: "ok",
  label: "Model-based scenario, not a forecast",
  checks: [],
  actual_sample: {
    start: "2000-Q1",
    end: "2025-Q3",
    nobs: 103,
    common_nobs: 107,
    periods: [],
    dropped_periods: [],
    frequency_conversion: {},
    transforms: {},
  },
  irf: {
    periods: [0, 1, 2],
    variables: ["gdp_real", "cpi", "unemp", "policy_rate"],
    values: [
      [0, 0, 0, 0.266245291587],
      [0.1, 0.05, 0.02, 0.2],
      [-0.4, -0.3, 0.1, 0.1],
    ],
    lower: [
      [0, 0, 0, 0.2],
      [0.01, -0.1, -0.1, 0.1],
      [-0.5, -0.4, -0.1, 0],
    ],
    upper: [
      [0, 0, 0, 0.3],
      [0.2, 0.2, 0.2, 0.3],
      [-0.2, -0.1, 0.2, 0.2],
    ],
    shock: "policy_rate",
    shock_size: 0.266245291587,
    band_level: 0.68,
    band_method: "bootstrap",
  },
  notes: [
    "The estimated output response rises after the tightening: full output diagnostic.",
    "The estimated price response rises after the tightening: full price diagnostic.",
    "Full technical method note retained for inspection.",
  ],
  sensitivity: {
    status: "available",
    variants: [],
    summary: [
      {
        variable: "gdp_real",
        baseline_peak_response: -0.4000123456789,
        baseline_peak_horizon: 2,
        peak_response_range: [-0.512345678901, 0.278901234567],
        peak_absolute_response_range: [0.278901234567, 0.512345678901],
        peak_horizon_range: [1, 2],
        sign_agreement_share: 0.5,
        comparable_alternatives: 2,
        baseline_band_excludes_zero_at_peak: true,
      },
    ],
  },
};
const result: AnalysisResult = {
  status: "ok",
  config_hash: "fixture-config",
  snapshot_id: "fixture",
  code_version: "fixture",
  runtime_ms: 100,
  label: country.label,
  config,
  checks: [],
  results: [country],
  actual_samples: { USA: country.actual_sample },
};
const manifest: Manifest = {
  snapshot_id: "fixture",
  as_of_date: "2026-10-21",
  countries: [{ iso3: "USA", name: "United States" }],
  indicators: [
    { concept_id: "gdp_real", title: "Real GDP" },
    { concept_id: "cpi", title: "Consumer prices" },
    { concept_id: "unemp", title: "Unemployment" },
    { concept_id: "policy_rate", title: "Policy rate" },
  ],
  templates: [],
  models: [],
  validation: {},
  sources: [],
  schema_url: "/schema.json",
};
const renderCountry = (compact: boolean, output: CountryResult = country) =>
  renderToStaticMarkup(
    <ResultsCountry
      result={output}
      manifest={manifest}
      comparison
      first
      cards={[]}
      compact={compact}
    />,
  );

describe("G3.1 result interpretation", () => {
  it("keeps short descriptive rankings outside technical disclosures", () => {
    const output = structuredClone(country);
    output.model_id = "desc.compare";
    delete output.irf;
    output.test_results = [
      {
        country: "USA",
        series: "policy_rate",
        method: "mean",
        statistic: 2,
        rank: 1,
      },
      {
        country: "CAN",
        series: "policy_rate",
        method: "mean",
        statistic: 1,
        rank: 2,
      },
    ];
    const before = structuredClone(output);
    const html = renderCountry(false, output);
    expect(html.indexOf('data-testid="short-result-summary"')).toBeGreaterThan(
      0,
    );
    expect(html.indexOf('data-testid="short-result-summary"')).toBeLessThan(
      html.indexOf('<details class="card technical-details">'),
    );
    expect(html.match(/Country comparison and rankings/g)).toHaveLength(1);
    expect(output).toEqual(before);
  });
  it("rounds the resolved standard-deviation shock only for display", () => {
    expect(shockHeading(country.irf!, config, manifest.indicators)).toBe(
      "Policy-rate shock: +0.27 pp (one standard deviation)",
    );
    const before = structuredClone(result);
    const rows = resultCsvRows(country);
    expect(
      rows.find(
        (row) =>
          row.record_type === "Impulse responses and pointwise intervals",
      )?.shock_size,
    ).toBe(0.266245291587);
    expect(
      rows.find((row) => row.record_type === "sensitivity_summary")
        ?.peak_response_range,
    ).toEqual([-0.512345678901, 0.278901234567]);
    expect(result).toEqual(before);
  });
  it("uses signed peak ranges, readable yes/no, and never substitutes absolute ranges", () => {
    const row = sensitivityRows(country, manifest.indicators)[0];
    expect(row["Signed peak range"]).toBe("-0.512 to 0.279");
    expect(row["Baseline band excludes zero"]).toBe("Yes");
    const withoutSigned = structuredClone(country);
    delete withoutSigned.sensitivity.summary![0].peak_response_range;
    withoutSigned.sensitivity.summary![0].baseline_band_excludes_zero_at_peak = false;
    expect(
      sensitivityRows(withoutSigned, manifest.indicators)[0],
    ).toMatchObject({
      "Signed peak range": "Not reported",
      "Baseline band excludes zero": "No",
    });
  });
  it("keeps the reading guide to five bullets and combines two conditional puzzle notes", () => {
    const bullets = readingBullets(country, manifest.indicators);
    expect(bullets).toHaveLength(5);
    expect(
      bullets.filter((bullet) => bullet.includes("output/price puzzle")),
    ).toHaveLength(1);
    expect(bullets.join(" ")).toContain(
      "Output and prices rise at some horizons",
    );
    expect(
      readingBullets({ ...country, notes: [] }, manifest.indicators).join(" "),
    ).not.toContain("puzzle");
    expect(
      chartData(country, manifest.indicators).every(
        (chart) => !chart.summary.includes("selected-peak"),
      ),
    ).toBe(true);
    expect(
      renderCountry(false).match(/Selected-peak comparisons are descriptive/g),
    ).toHaveLength(1);
  });
  it("puts the actual estimation sample in the three-line mobile summary", () => {
    const summary = mobileSummaryLines(result);
    expect(summary).toHaveLength(3);
    expect(summary[0]).toBe("+0.27 pp policy shock · 1 SD");
    expect(summary[1]).toContain("2000-Q1–2025-Q3 · n = 103");
    expect(summary.join(" ")).not.toContain("1999-Q1");
  });
  it("does not turn unavailable sign agreement into zero percent", () => {
    const output = structuredClone(country);
    output.sensitivity.summary![0].sign_agreement_share = null;
    expect(
      sensitivityRows(output, manifest.indicators)[0][
        "Same sign at baseline peak"
      ],
    ).toBe("Not reported");
    delete output.irf;
    expect(sensitivityRows(output, manifest.indicators)[0]["Same sign"]).toBe(
      "Not reported",
    );
  });
  it("does not describe an easing response as a tightening puzzle", () => {
    const output = structuredClone(country);
    output.irf!.shock_size = -0.25;
    expect(readingBullets(output, manifest.indicators).join(" ")).not.toContain(
      "puzzle",
    );
  });
  it("stacks all mobile charts and short summaries while disclosing detailed tables", () => {
    const mobile = renderCountry(true);
    const desktop = renderCountry(false);
    expect(mobile.match(/data-testid="result-chart"/g)).toHaveLength(4);
    expect(mobile).toContain('data-testid="export-chart-selector"');
    expect(mobile).toContain('data-testid="mobile-sensitivity-cards"');
    expect(mobile).toContain(
      "Full technical method note retained for inspection.",
    );
    expect(mobile).toContain("Tables, diagnostics and full method notes");
    expect(desktop.match(/data-testid="result-chart"/g)).toHaveLength(4);
    expect(desktop).not.toContain('data-testid="mobile-chart-selector"');
    expect(mobile).toContain(
      "<summary>Tables, diagnostics and full method notes</summary>",
    );
    expect(mobile).toContain(
      "<summary>Every specification and its sample</summary>",
    );
    expect(mobile).not.toContain("<summary>Variant estimates</summary>");
  });
  it("offers explicit interactive and precise bootstrap choices", () => {
    const html = renderToStaticMarkup(
      <Results
        result={result}
        manifest={manifest}
        bundles={{}}
        busy={false}
        rerun={vi.fn()}
        exportPython={vi.fn()}
        share={vi.fn()}
        shareUrl=""
        edit={vi.fn()}
      />,
    );
    expect(html).toContain("Interactive · 200 draws");
    expect(html).toContain("Precise · 1,000 draws");
    expect(html).toContain('data-testid="bootstrap-precision"');
    expect(html).toContain('data-testid="result-details"');
    expect(html).not.toContain('<details class="result-details');
    expect(html).not.toContain('aria-label="Result panels"');
    expect(html).not.toContain('class="result-response-content" hidden');
  });
  it("exports the first available chart when an earlier country is blocked", () => {
    const mixed = structuredClone(result);
    mixed.results.unshift({
      ...structuredClone(country),
      country: "GBR",
      status: "blocked",
    });
    const html = renderToStaticMarkup(
      <Results
        result={mixed}
        manifest={manifest}
        bundles={{}}
        busy={false}
        rerun={vi.fn()}
        exportPython={vi.fn()}
        share={vi.fn()}
        shareUrl=""
        edit={vi.fn()}
      />,
    );
    expect(html.match(/data-export-owner="true"/g)).toHaveLength(1);
  });
  it("shows lag criteria with the comparison sample and preserves unrounded evidence", () => {
    const output = structuredClone(country);
    const criteria = {
      status: "available",
      candidates: [
        { lag: 0, aic: -4.123456789, bic: -3.987654321, hqic: -4.012345678 },
      ],
      selected_lags: { aic: 4, bic: 2, hqic: 2 },
      comparison_sample: { start: "2000-Q3", end: "2025-Q3", nobs: 101 },
      interpretation: "Lower is preferred within each criterion.",
    };
    Object.assign(output.sensitivity, { lag_criteria: criteria });
    const html = renderCountry(true, output);
    expect(html).toContain("Lag selection · AIC 4 · BIC 2 · HQIC 2");
    expect(html).toContain("2000-Q3–2025-Q3 · n = 101");
    expect(
      resultCsvRows(output).find(
        (row) => row.record_type === "sensitivity_definition",
      )?.lag_criteria,
    ).toEqual(criteria);
    expect(specificationLabel({ variant_id: "extended_var" })).toBe(
      "Extended VAR · exchange rate and credit",
    );
  });
  it("renders an important small-sample warning once, without filtering it away", () => {
    const output = {
      ...country,
      checks: [
        {
          code: "small_sample",
          level: "warn",
          message: "Only 105 observations for 13 parameters per equation.",
          country: "USA",
        },
      ],
    };
    const html = renderCountry(true, output);
    expect(html).toContain('aria-label="Important warnings"');
    expect(
      html.match(
        /<span>Only 105 observations for 13 parameters per equation\.<\/span>/g,
      ),
    ).toHaveLength(1);
  });
});
