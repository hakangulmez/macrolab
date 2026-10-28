import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import {
  addFlowX,
  blankAnalysis,
  changeFlowModel,
  chooseShock,
  chooseY,
  flowY,
  reconcileOrder,
  removeFlowX,
} from "../src/builderFlow";
import { VariableFirstBuilder } from "../src/components/VariableFirstBuilder";
import { builderGuidance } from "../src/builderGuidance";
import type { AnalysisConfig, Manifest } from "../src/types";
const manifest = JSON.parse(
  readFileSync(
    new URL("./fixtures/builder-manifest.json", import.meta.url),
    "utf8",
  ),
) as Manifest;
const history = JSON.parse(
  readFileSync(
    new URL("./fixtures/builder-history.json", import.meta.url),
    "utf8",
  ),
) as { version: string; config: AnalysisConfig }[];
const indicator = (id: string) =>
  manifest.indicators.find((i) => i.concept_id === id)!;
function regression() {
  const c = blankAnalysis(manifest);
  const next = addFlowX(chooseY(c, indicator("cpi")), indicator("unemp"));
  next.countries = ["KOR", "CAN"];
  next.model.params = { covariance: "HAC", hac_lags: 4 };
  next.sample = { start: "2001-Q1", end: "2025-Q4" };
  return next;
}
function markup(
  config: AnalysisConfig,
  mode: "simple" | "advanced" = "simple",
) {
  return renderToStaticMarkup(
    <VariableFirstBuilder
      mode={mode}
      manifest={manifest}
      config={config}
      setConfig={vi.fn()}
      bundles={{}}
      models={null}
      checks={[]}
      busy={false}
      run={vi.fn()}
      check={vi.fn()}
      fix={vi.fn()}
    />,
  );
}
describe("Variable-first builder preservation and model semantics", () => {
  it("renders Y, X, model and countries in order, with Run outside the collapsed settings", () => {
    const html = markup(regression());
    const positions = [
      "flow-y-heading",
      "flow-x-heading",
      "flow-model-heading",
      "flow-countries-heading",
    ].map((x) => html.indexOf(`id="${x}"`));
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    expect(html).toContain('<details class="flow-settings">');
    expect(html.indexOf('data-testid="run-analysis"')).toBeGreaterThan(
      html.lastIndexOf("</details>"),
    );
    expect((html.match(/data-testid="run-analysis"/g) ?? []).length).toBe(1);
  });
  it("does not mutate the accepted template fixtures in either mode", () => {
    for (const template of manifest.templates) {
      const c = structuredClone(template.config),
        before = JSON.stringify(c);
      markup(c);
      markup(c, "advanced");
      expect(JSON.stringify(c)).toBe(before);
    }
  });
  it("preserves all ten historical configurations through Simple/Advanced rendering", () => {
    for (const row of history) {
      const before = structuredClone(row.config);
      markup(row.config);
      markup(row.config, "advanced");
      expect(row.config, row.version).toEqual(before);
    }
  });
  it("keeps an existing external control external when selecting a system model", () => {
    const c = regression();
    c.series[1].role = "exogenous";
    const next = changeFlowModel(c, "fc.var");
    expect(next.series[1]).toEqual(c.series[1]);
  });
  it("retains custom settings and recursive ordering through rendering and transform edits", () => {
    const c = structuredClone(
      manifest.templates.find((t) => t.id === "monetary_policy")!.config,
    );
    c.identification!.params.order.reverse();
    c.outputs.irf!.draws = 500;
    c.model.params.custom_future_field = { keep: true };
    const before = structuredClone(c);
    markup(c);
    markup(c, "advanced");
    expect(c).toEqual(before);
    c.series[1].transform = "log";
    reconcileOrder(c);
    expect(c.identification).toEqual(before.identification);
  });
  it("replaces only Y, keeping X transforms, sample, countries and method parameters", () => {
    const c = regression(),
      before = structuredClone(c);
    const next = chooseY(c, indicator("gdp_real"));
    expect(flowY(next)?.concept_id).toBe("gdp_real");
    expect(next.series[1]).toEqual(c.series[1]);
    expect(next.countries).toEqual(c.countries);
    expect(next.sample).toEqual(c.sample);
    expect(next.model).toEqual(c.model);
    expect(c).toEqual(before);
  });
  it("promotes an existing X without duplicates or changing its transformation", () => {
    const c = regression();
    c.series[1].transform = "diff";
    const next = chooseY(c, indicator("unemp"));
    expect(flowY(next)).toMatchObject({
      concept_id: "unemp",
      role: "dependent",
      transform: "diff",
    });
    expect(next.series.find((s) => s.concept_id === "cpi")?.role).toBe(
      "regressor",
    );
    expect(new Set(next.series.map((s) => s.concept_id)).size).toBe(2);
  });
  it("adds/removes only the requested X and never converts a multi-country regression into a panel", () => {
    const c = regression(),
      next = addFlowX(c, indicator("reer"));
    expect(next.series[2]).toMatchObject({
      concept_id: "reer",
      role: "regressor",
    });
    expect(next.model).toEqual(c.model);
    expect(next.countries).toEqual(["KOR", "CAN"]);
    expect(removeFlowX(next, "reer")).toEqual(c);
    expect(
      builderGuidance(
        c,
        manifest.models.find((m) => m.id === c.model.id)!,
      ),
    ).toEqual([]);
  });
  it("keeps every selected series when changing to forecasting, requiring an explicit future X path", () => {
    const c = regression(),
      next = changeFlowModel(c, "uni.arima");
    expect(next.series.map((s) => s.role)).toEqual(["dependent", "exogenous"]);
    expect(next.series.map((s) => s.transform)).toEqual(
      c.series.map((s) => s.transform),
    );
    expect(next.sample).toEqual(c.sample);
    expect(
      builderGuidance(
        next,
        manifest.models.find((m) => m.id === "uni.arima")!,
      ).join(" "),
    ).toContain("explicit future path");
  });
  it("starts a reduced-form VAR without silently enabling shock identification", () => {
    const next = changeFlowModel(regression(), "var.ols");
    expect(next.identification).toBeNull();
    expect(next.outputs.irf).toBeUndefined();
    expect(
      builderGuidance(
        next,
        manifest.models.find((m) => m.id === "var.ols")!,
      ),
    ).toEqual([]);
  });
  it("adds global factors as external controls in a system model", () => {
    const c = changeFlowModel(regression(), "var.ols");
    const next = addFlowX(c, indicator("oil_brent"));
    expect(next.series.at(-1)?.role).toBe("exogenous");
  });
  it("requires an explicit shock instead of inventing one from the X list", () => {
    const c = changeFlowModel(regression(), "lp.ols");
    expect(c.series.some((s) => s.role === "shock")).toBe(false);
    const next = chooseShock(c, "unemp");
    expect(next.series.map((s) => s.role)).toEqual(["response", "shock"]);
    expect(
      builderGuidance(
        next,
        manifest.models.find((m) => m.id === "lp.ols")!,
      ),
    ).toEqual([]);
  });
  it("leaves same-model custom parameters untouched", () => {
    const c = regression();
    expect(changeFlowModel(c, c.model.id)).toEqual(c);
  });
  it("renders an empty custom analysis with Run disabled and no selected country or variable", () => {
    const c = blankAnalysis(manifest),
      html = markup(c);
    expect(c.countries).toEqual([]);
    expect(c.series).toEqual([]);
    expect(html).toMatch(/data-testid="run-analysis"[^>]*disabled/);
  });
});
