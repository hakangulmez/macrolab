import { describe, expect, it } from "vitest";
import { niceScale, tickLabel } from "../src/chartScale";
import { countryIndicators } from "../src/displayLabels";
import { coefficientInterval } from "../src/resultData";
import { exportText } from "../src/pngExport";
import { buildVersion } from "../src/version";

describe("G8 presentation contracts", () => {
  it.each([
    [-0.0073, 0.0021],
    [-111, 1],
    [0, 0],
    [1e-7, 2e-7],
    [-1, -0.2],
  ])("contains a labelled zero and readable ticks: %s", (...values) => {
    const axis = niceScale(values);
    expect(axis.ticks).toContain(0);
    expect(tickLabel(0, axis.step)).toBe("0");
    expect(axis.min).toBeLessThanOrEqual(Math.min(...values));
    expect(axis.max).toBeGreaterThanOrEqual(Math.max(...values));
    const labels = axis.ticks.map((t) => tickLabel(t, axis.step));
    expect(labels.some((l) => /e[-+]/i.test(l))).toBe(false);
    expect(new Set(labels).size).toBe(labels.length);
  });
  it("uses geography only for display, preserving source objects", () => {
    const input = [
      { concept_id: "cpi", title: "generic" },
      { concept_id: "policy_rate", title: "ECB for EA members" },
    ];
    expect(countryIndicators(input, "USA").map((i) => i.title)).toEqual([
      "CPI · headline prices",
      "Policy rate",
    ]);
    expect(countryIndicators(input, "DEU").map((i) => i.title)).toEqual([
      "HICP · headline prices",
      "Policy rate · ECB",
    ]);
    expect(countryIndicators(input, "POL")[1].title).not.toContain("ECB");
    expect(countryIndicators(input, "TUR")[0].title).toContain("CPI");
    expect(input[0].title).toBe("generic");
  });
  it("coefficient legend reports actual covariance and confidence, not pointwise", () => {
    const label = coefficientInterval({
      diagnostics: { covariance: "HC1", confidence: 0.9 },
    });
    expect(label).toBe("90% confidence interval (HC1)");
    const text = exportText(
      [
        {
          name: "Coefficients",
          unit: "units",
          points: [],
          summary: "",
          coefficient: true,
          intervalLabel: label,
        },
      ],
      {
        analysis: "Taylor",
        country: "GBR",
        sample: "2000–2008",
        frequency: "Q",
        sources: ["OECD"],
        bandLevel: 0.9,
        comparisonLabel: "",
        horizon: false,
      },
    );
    expect(text.legend).toContain(label);
    expect(text.legend).not.toContain("pointwise");
    expect(text.footer).toContain(buildVersion);
  });
});

it("country panels share scales per response and preserve each response's sample", async () => {
  const { countryPanels } = await import("../src/comparisonData");
  const result = {
    results: ["DEU", "ESP"].map((country, i) => ({
      country,
      status: "ok",
      model_id: "cmp.common_shock",
      actual_sample: {
        start: "2000-Q1",
        end: "2023-Q4",
        nobs: 96,
        transforms: {},
      },
      response_results: {
        cpi: {
          actual_sample: { start: "2001-Q1", end: "2022-Q4", nobs: 88 },
          local_projection: {
            response_mode: "cumulative_log",
            response_definition: "cumulative % change in the level",
          },
        },
      },
      irf: {
        periods: [0, 1],
        variables: ["gdp_real", "cpi"],
        values: [
          [0, 0],
          [i + 1, -(i + 1) * 0.01],
        ],
        lower: [
          [-0.1, -0.01],
          [i + 0.5, -0.04],
        ],
        upper: [
          [0.1, 0.01],
          [i + 1.5, 0.02],
        ],
        band_level: 0.68,
      },
    })),
  };
  const manifest = {
    countries: [
      { iso3: "DEU", name: "Germany" },
      { iso3: "ESP", name: "Spain" },
    ],
    indicators: [
      { concept_id: "cpi", title: "generic" },
      { concept_id: "gdp_real", title: "Real GDP" },
    ],
  };
  const charts = countryPanels(
    result as unknown as import("../src/types").AnalysisResult,
    manifest as unknown as import("../src/types").Manifest,
  );
  expect(charts[0].axis).toEqual(charts[1].axis);
  expect(charts[2].axis).toEqual(charts[3].axis);
  expect(charts[0].axis).not.toEqual(charts[2].axis);
  expect(charts[2].transformation).toContain("2001-Q1–2022-Q4 · n=88");
  expect(charts[2].name).toContain("HICP");
});
