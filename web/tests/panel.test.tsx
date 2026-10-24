import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PanelControls } from "../src/components/PanelControls";
import { PanelResults } from "../src/components/PanelResults";
import {
  analysisCsvRows,
  chartData,
  panelSourceNames,
} from "../src/resultData";
import type {
  AnalysisConfig,
  CountryResult,
  CountryBundle,
  Manifest,
} from "../src/types";
const manifest = {
  countries: [
    { iso3: "DEU", name: "Germany" },
    { iso3: "FRA", name: "France" },
  ],
  indicators: [],
  templates: [],
} as unknown as Manifest;
it("explains why time effects are disabled for common shocks", () => {
  const config = {
    countries: ["DEU", "FRA"],
    model: { id: "panel.lp", params: { shock_type: "common" } },
  } as unknown as AnalysisConfig;
  const html = renderToStaticMarkup(
    <PanelControls config={config} manifest={manifest} update={() => {}} />,
  );
  expect(html).toContain('value="two_way" disabled=""');
  expect(html).toContain("because they absorb the shock");
  config.model.params.shock_type = "country_specific";
  expect(
    renderToStaticMarkup(
      <PanelControls config={config} manifest={manifest} update={() => {}} />,
    ),
  ).not.toContain('value="two_way" disabled=""');
});
it("puts country OLS beside pooled coefficients, preserving full CSV precision", () => {
  const r = {
    country: "POOLED",
    model_id: "panel.fe",
    status: "ok",
    label: "association",
    checks: [],
    coefficients_table: [{ term: "x", estimate: 0.123456789 }],
    actual_sample: { transforms: {} },
    sensitivity: { status: "ok", variants: [] },
    panel: {
      N: 2,
      T_min: 80,
      T_max: 90,
      total_observations: 170,
      effects: "country",
      covariance: "Driscoll-Kraay",
      country_samples: { DEU: { nobs: 80 }, FRA: { nobs: 90 } },
      country_estimates: {
        DEU: [{ term: "x", estimate: 0.246813579 }],
        FRA: [{ term: "x", estimate: -0.135791357 }],
      },
    },
  } as unknown as CountryResult;
  const html = renderToStaticMarkup(
    <PanelResults result={r} manifest={manifest} />,
  );
  expect(html).toContain("Pooled");
  expect(html).toContain("Germany");
  expect(html).toContain("France");
  expect(html).toContain("0.123");
  expect(chartData(r, []).some((c) => c.coefficient)).toBe(true);
  const rows = analysisCsvRows({
    results: [r],
    snapshot_id: "fixture",
    config_hash: "fixture",
  });
  expect(JSON.stringify(rows)).toContain("0.246813579");
  expect(JSON.stringify(rows)).toContain("country_samples");
  expect(
    rows.find((r) => r.record_type === "Country estimates: DEU")
      ?.actual_sample_nobs,
  ).toBe(80);
});

it("attributes the selected ECB DFR in pooled PNGs instead of the base policy source", () => {
  const config = {
    countries: ["DEU"],
    series: [{ concept_id: "policy_rate" }, { concept_id: "gdp_real" }],
    model: { id: "panel.lp", params: { first_stage_source: "ecb_dfr" } },
  } as unknown as AnalysisConfig;
  const bundles = {
    DEU: {
      cards: [
        { concept_id: "policy_rate", source_segments: [{ source: "BIS" }] },
        { concept_id: "gdp_real", source_segments: [{ source: "OECD" }] },
      ],
    },
    USA: {
      cards: [
        { concept_id: "gdp_real", source_segments: [{ source: "Unused" }] },
      ],
    },
  } as unknown as Record<string, CountryBundle>;
  expect(panelSourceNames(config, bundles)).toEqual(["ECB", "OECD"]);
  config.model.params.first_stage_source = "selected";
  expect(panelSourceNames(config, bundles)).toEqual(["BIS", "OECD"]);
});
