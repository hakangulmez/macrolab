import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Builder } from "../src/components/Builder";
import type { AnalysisConfig, CountryBundle, Manifest } from "../src/types";

const config: AnalysisConfig = {
  schema_version: 1,
  snapshot_id: "synthetic",
  countries: ["USA"],
  series: [
    { concept_id: "policy_rate", role: "shock", transform: "level" },
    { concept_id: "gdp_real", role: "endogenous", transform: "yoy_pct" },
  ],
  frequency: "Q",
  aggregation: { policy_rate: "mean", gdp_real: "mean" },
  sample: { start: "1999-Q1", end: "latest" },
  special_periods: { covid: "dummy" },
  model: { id: "var.ols", params: {} },
  identification: {
    id: "recursive",
    params: { order: ["policy_rate", "gdp_real"] },
  },
  outputs: {
    irf: {
      horizon: 12,
      bands: 0.68,
      shock_size: 1,
      shock_mode: "one_sd",
      method: "bootstrap",
      draws: 200,
    },
  },
  comparison: {},
  seed: 42,
};
const manifest: Manifest = {
  snapshot_id: "synthetic",
  as_of_date: "2026-10-21",
  schema_url: "/schema.json",
  validation: {},
  sources: [],
  templates: [],
  countries: [{ iso3: "USA", name: "United States" }],
  indicators: [
    { concept_id: "policy_rate", title: "Policy rate", frequency: "M" },
    { concept_id: "gdp_real", title: "Real GDP", frequency: "Q" },
  ],
  models: [
    {
      id: "var.ols",
      title: "VAR",
      family: "multivariate",
      summary: "Dynamic associations",
      label: "Association, not causation",
      assumptions: [],
      inputs: {},
      params: {},
      references: [],
      runtime: "browser",
    },
  ],
};
const bundle: CountryBundle = {
  country: manifest.countries[0],
  snapshot_id: "synthetic",
  profiles: [],
  series: {},
  cards: manifest.indicators.map((indicator) => ({
    ...indicator,
    status: "available",
    first_date: "1999-Q1",
    last_date: "2026-Q2",
    sources: ["BIS"],
    source_segments: [],
    flags: [],
    warnings: [],
    reason_codes: [],
    stale: false,
  })),
};
const render = (
  value = config,
  runtimeStatus = "idle",
  busy = false,
  data = manifest,
) =>
  renderToStaticMarkup(
    <Builder
      manifest={data}
      config={value}
      setConfig={vi.fn()}
      bundles={{ USA: bundle }}
      models={null}
      checks={[]}
      busy={busy}
      runtimeStatus={runtimeStatus}
      run={vi.fn()}
      check={vi.fn()}
      fix={vi.fn()}
      openSource={vi.fn()}
    />,
  );

describe("Compact Builder", () => {
  it("counts included factors dynamically and excludes withheld concepts from selection", () => {
    const candidate = {
      ...manifest,
      publication: { included_global_factors: ["oil_brent", "us_policy_rate"] },
      indicators: [
        ...manifest.indicators,
        { concept_id: "oil_brent", title: "Brent", scope: "global" },
        {
          concept_id: "us_policy_rate",
          title: "US policy factor",
          scope: "global",
        },
        {
          concept_id: "commod_idx",
          title: "Withheld commodity index",
          scope: "global",
          publication: { included: false },
        },
      ],
    } as Manifest;
    const html = render(config, "idle", false, candidate);
    expect(html).toContain(
      'placeholder="Search 2 indicators + 2 included global factors"',
    );
    expect(html).toContain("Brent");
    expect(html).not.toContain("Withheld commodity index");
  });
  it("shows preparation and readiness beside Run without locking the editable Builder", () => {
    const preparing = render(config, "preparing");
    expect(preparing).toContain(
      "Preparing the analysis engine… You can keep editing.",
    );
    expect(preparing).toContain(
      'data-testid="runtime-readiness" data-runtime-status="preparing"',
    );
    expect(
      preparing.match(/<button[^>]*data-testid="run-analysis"[^>]*>/)?.[0],
    ).not.toContain("disabled");
    const ready = render(config, "ready");
    expect(ready).toContain("Ready to calculate locally.");
    expect(
      ready.match(/<button[^>]*data-testid="run-analysis"[^>]*>/)?.[0],
    ).not.toContain("disabled");
    const running = render(config, "ready", true);
    expect(running).toContain("Working locally…");
    expect(running).not.toContain("Ready to calculate locally.");
    expect(
      running.match(/<button[^>]*data-testid="run-analysis"[^>]*>/)?.[0],
    ).toContain("disabled");
  });
  it("uses short visible labels and uniquely labelled accessible controls", () => {
    const html = render();
    expect(html.match(/<span>Role<\/span>/g)).toHaveLength(2);
    expect(html.match(/<span>Transform<\/span>/g)).toHaveLength(2);
    expect(html).toContain('aria-label="Role for Real GDP"');
    expect(html).toContain('aria-label="Transform for Policy rate"');
    expect(html).not.toContain("Role: Real GDP");
    expect(html).not.toContain("Transform: Policy rate");
    expect(html.match(/class="compact-series"/g)).toHaveLength(2);
  });
  it("keeps aggregation and transformation details under Advanced while coverage stays visible", () => {
    const html = render();
    const visible = html.replace(/<details\b[^>]*>[\s\S]*?<\/details>/g, "");
    expect(html).toContain('<details class="compact-series-advanced">');
    expect(html).toContain("Aggregation for Real GDP");
    expect(visible).not.toContain("Aggregation");
    expect(visible).toContain("1999-Q1");
    expect(visible).toContain("2026-Q2");
    expect(visible).toContain("Available");
    expect(visible).toContain('class="compact-coverage-link"');
  });
  it("offers interactive and precise draw choices without silently changing existing configurations", () => {
    const current = structuredClone(config);
    current.outputs.irf!.draws = 500;
    const html = render(current);
    expect(html).toContain("Bootstrap precision");
    expect(html).toContain(
      '<option value="200">Interactive · 200 draws</option>',
    );
    expect(html).toContain(
      '<option value="1000">Precise · 1,000 draws</option>',
    );
    expect(html).toContain(
      '<option value="500" selected="">Current · 500 draws</option>',
    );
    expect(current.outputs.irf!.draws).toBe(500);
  });
});
