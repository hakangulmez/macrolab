import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TemplateControls } from "../src/components/TemplateControls";
import { analysisCsvRows } from "../src/resultData";
import type {
  AnalysisConfig,
  AnalysisResult,
  CountryResult,
} from "../src/types";

it("does not give new pooled or forecast templates the legacy Türkiye controls", () => {
  for (const id of [
    "ea_phillips_pooled",
    "same_ecb_shock_pooled",
    "ea_inflation_horse_race",
  ]) {
    const config = {
      model: { params: { template_id: id } },
    } as unknown as AnalysisConfig;
    const html = renderToStaticMarkup(
      <TemplateControls config={config} update={() => {}} />,
    );
    expect(html).toContain("Template assumptions");
    expect(html).not.toContain("Türkiye pass-through");
    if (id === "ea_phillips_pooled") expect(html).toContain("two-sided");
    if (id === "same_ecb_shock_pooled")
      expect(html).toContain("Time effects would absorb");
    if (id === "ea_inflation_horse_race")
      expect(html).toContain("40 usable quarters");
  }
});

it("exports both outcomes and every specification with full-precision estimates", () => {
  const row = {
    country: "POOLED",
    model_id: "panel.lp",
    status: "ok",
    outcome: "cpi",
    checks: [],
    actual_sample: { start: "2000-Q3", end: "2021-Q2", nobs: 336 },
    sensitivity: { variants: [] },
    coefficients_table: [{ term: "shock", estimate: -0.5860699386295264 }],
  } as unknown as CountryResult;
  const r = {
    snapshot_id: "fixture",
    config_hash: "fixture",
    results: [row, { ...row, outcome: "gdp_real" }],
    template_notes: ["Conditional bands ignore first-stage uncertainty."],
    template_sensitivity: [{ id: "end_2019", status: "ok", results: [row] }],
  } as unknown as AnalysisResult;
  const rows = analysisCsvRows(r);
  expect(rows.some((r) => r.outcome === "gdp_real")).toBe(true);
  expect(
    rows.some(
      (r) =>
        r.specification === "end_2019" && r.estimate === -0.5860699386295264,
    ),
  ).toBe(true);
  expect(rows.some((r) => r.record_type === "template_note")).toBe(true);
});

it("preserves the legacy ECB CSV format when a national VAR sensitivity has compact results", () => {
  const result = {
    snapshot_id: "fixture",
    config_hash: "fixture",
    results: [
      {
        country: "DEU",
        model_id: "lp.ols",
        status: "ok",
        checks: [],
        actual_sample: { start: "2000-Q3", end: "2021-Q2", nobs: 84 },
        sensitivity: { variants: [] },
      },
    ],
  } as unknown as AnalysisResult;
  expect(
    analysisCsvRows({
      ...result,
      template_notes: ["Legacy note"],
      template_sensitivity: [
        { variant_id: "national_var", results: [{ country: "DEU" }] },
      ],
    } as unknown as AnalysisResult),
  ).toEqual(analysisCsvRows(result));
});
