import { afterEach, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { initialTheme } from "../src/theme";
import { datasetCounts } from "../src/uiData";
import { latexTables } from "../src/latexExport";
import { ResultRail, ResultTableView } from "../src/components/ResultOverview";
import type { AnalysisResult, Manifest } from "../src/types";
afterEach(() => vi.unstubAllGlobals());
it("respects saved choice, system preference, then dark, including blocked storage", () => {
  vi.stubGlobal("localStorage", { getItem: () => "light" });
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  expect(initialTheme()).toBe("light");
  vi.stubGlobal("localStorage", {
    getItem: () => {
      throw Error("blocked");
    },
  });
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: q.includes("light"),
  }));
  expect(initialTheme()).toBe("light");
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  expect(initialTheme()).toBe("dark");
});
const manifest = {
  countries: [{ iso3: "DEU", name: "Germany" }],
  indicators: [{ concept_id: "cpi", title: "HICP", scope: "national" }],
  templates: [],
  models: [],
  coverage: [
    { country: "DEU", concept_id: "cpi", status: "limited", observations: 20 },
    { country: "FRA", concept_id: "cpi", status: "missing", observations: 0 },
  ],
} as unknown as Manifest;
it("counts populated series independently of economy-indicator cells", () => {
  expect(datasetCounts(manifest)).toMatchObject({
    cells: 2,
    populated: 1,
    statuses: { limited: 1, missing: 1 },
  });
});
const result = {
  code_version: "2.0.0",
  snapshot_id: "fixture",
  config_hash: "fixture",
  status: "ok",
  checks: [],
  config: { countries: ["DEU"] },
  results: [
    {
      country: "DEU",
      model_id: "sing.ols",
      actual_sample: {
        start: "2000-Q1",
        end: "2020-Q1",
        nobs: 81,
        dropped_periods: [],
      },
      coefficients_table: [
        {
          term: "A&B_%",
          estimate: 0.12345678901234566,
          std_error: 0.000004321,
          lower: -0.87,
          upper: 0.98,
        },
      ],
      panel: {
        country_samples: {
          DEU: { start: "2000-Q1", end: "2020-Q1", nobs: 81 },
        },
      },
      sensitivity: { variants: [] },
    },
  ],
  template_sensitivity: [
    {
      id: "national",
      label: "Different identification",
      same_estimand: false,
      include_in_agreement_counts: false,
    },
    {
      id: "different",
      label: "Alternative sample",
      comparison: [{ outcome: "cpi", material: true }],
    },
  ],
} as unknown as AnalysisResult;
it("serializes full precision into LaTeX without mutating any result or replacing legacy exports", () => {
  const before = JSON.stringify(result),
    tex = latexTables(result, manifest);
  expect(tex).toContain("0.12345678901234566"); // exact JS representation, no display rounding
  expect(tex).toContain("0.000004321");
  expect(tex).toContain("\\&");
  expect(tex).toContain("\\_");
  expect(tex).toContain("MacroLab v2.1.0; scientific runtime 2.0.0");
  expect(JSON.stringify(result)).toBe(before);
});
it("keeps material flags and different-estimand exclusions distinct in the compact rail", () => {
  const html = renderToStaticMarkup(
    <ResultRail
      result={result}
      manifest={manifest}
      showResponse={() => {}}
      exportCsv={() => {}}
      exportPython={() => {}}
      exportPng={() => {}}
      exportLatex={() => {}}
      busy={false}
    />,
  );
  expect(html).toContain("Changes the answer");
  expect(html).toContain("Different estimand");
  expect(html).toContain("Excluded from same-estimand agreement");
  expect(html).not.toContain("same-sign");
});
it("shows per-country samples in the Samples tab, including observations as integers", () => {
  const html = renderToStaticMarkup(
    <ResultTableView result={result} manifest={manifest} tab="samples" />,
  );
  expect(html).toContain("Germany");
  expect(html).toContain(">81<");
  expect(html).not.toContain(">81.0<");
});

it("uses approved sensitivity copy only in the UI and labels rolling mode accurately", async () => {
  const { sensitivityDisplayLabel } = await import("../src/sensitivityLabels");
  const { specificationLabel } = await import("../src/resultData");
  const pairs = [
    ["lags 4", "4 lags"],
    ["lags 6", "6 lags"],
    ["hac", "HAC inference"],
    ["covariance HC1", "HC1 standard errors"],
    ["recent half", "Recent half of the sample"],
    ["end 2019", "End sample in 2019"],
    ["common window", "Common sample window"],
    ["country-clustered", "Country-clustered standard errors"],
    ["conventional", "Conventional standard errors"],
    [
      "different method and different identification",
      "National VAR · different method and different identification",
    ],
  ];
  for (const [label, expected] of pairs) {
    const row = Object.freeze({ label });
    expect(sensitivityDisplayLabel(row)).toBe(expected);
    expect(specificationLabel(row)).toBe(label);
  }
  const rolling = {
    variant_id: "requested_sing.rolling",
    config: { model: { params: { mode: "rolling", window: 40 } } },
  };
  const original = JSON.stringify(rolling);
  expect(sensitivityDisplayLabel(rolling)).toBe("Rolling-window regression");
  expect(specificationLabel(rolling)).toBe("requested sing.rolling");
  expect(JSON.stringify(rolling)).toBe(original);
  expect(
    sensitivityDisplayLabel({
      ...rolling,
      config: { model: { params: { mode: "recursive" } } },
    }),
  ).toBe("requested sing.rolling");
});
