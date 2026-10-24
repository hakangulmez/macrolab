import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BvarControls } from "../src/components/BvarControls";
import { BvarResults } from "../src/components/BvarResults";
import {
  chartData,
  resultTableBlocks,
  sensitivityRows,
} from "../src/resultData";
import type { AnalysisConfig, CountryResult, Manifest } from "../src/types";
const manifest = {
  countries: [],
  indicators: [],
  templates: [],
} as unknown as Manifest;
const result = {
  country: "USA",
  model_id: "bvar.minn",
  status: "ok",
  actual_sample: { transforms: {} },
  irf: {
    variables: ["x", "policy"],
    periods: [0, 1],
    values: [
      [0, 1],
      [0.1, 0.4],
    ],
    lower: [
      [0, 1],
      [0, 0.2],
    ],
    upper: [
      [0, 1],
      [0.2, 0.6],
    ],
    band_level: 0.68,
  },
  bvar: {
    prior: {
      lambda_: 0.2,
      lag_decay: 2,
      own_first_lag_mean: { x: 0, policy: 1 },
      ar_residual_scales: { x: 0.5, policy: 1 },
      constant_variance: 1e8,
    },
    lambda_selection: "fixed",
    draws: {
      requested: 1000,
      retained: 1000,
      explosive: 20,
      explosive_share: 0.02,
      dropped: 0,
    },
    bands: {
      "0.68": {
        lower: [
          [0, 1],
          [0, 0.2],
        ],
        upper: [
          [0, 1],
          [0.2, 0.6],
        ],
      },
      "0.9": {
        lower: [
          [0, 1],
          [-0.1, 0.1],
        ],
        upper: [
          [0, 1],
          [0.3, 0.7],
        ],
      },
    },
    matched_ols: {
      status: "ok",
      values: [
        [0, 1],
        [0.15, 0.45],
      ],
    },
  },
  fevd: {
    values: [
      [
        [1, 0],
        [0.3, 0.7],
      ],
    ],
  },
  sensitivity: { variants: [] },
} as unknown as CountryResult;
it("labels posterior uncertainty distinctly and retains both band levels in exports", () => {
  const charts = chartData(result, []);
  expect(charts[0].intervalLabel).toBe("68% posterior credible band");
  expect(charts[0].summary).toContain("posterior credible");
  expect(sensitivityRows(result, [])[0]["Matched OLS peak"]).toBe("0.150");
  const blocks = resultTableBlocks(result);
  expect(JSON.stringify(blocks)).toContain("90% posterior credible bands");
  expect(JSON.stringify(blocks)).toContain("Posterior draw accounting");
  const html = renderToStaticMarkup(
    <BvarResults result={result} manifest={manifest} />,
  );
  expect(html).toContain("symmetrically");
  expect(html).toContain("retained");
  expect(html).toContain("OLS VAR");
  expect(html).not.toContain("confidence interval");
});
it("exposes fixed lambda and seeded draws without silently enabling optional priors", () => {
  const config = {
    countries: ["USA"],
    model: { id: "bvar.minn", params: {} },
    series: [
      { concept_id: "x", role: "response", transform: "qoq_saar" },
      { concept_id: "policy", role: "shock", transform: "level" },
    ],
  } as unknown as AnalysisConfig;
  const html = renderToStaticMarkup(
    <BvarControls config={config} manifest={manifest} update={() => {}} />,
  );
  expect(html).toContain("Fixed λ (default 0.2)");
  expect(html).toContain("5,000 seeded draws");
  expect(html).not.toContain('checked=""');
  expect(html).toContain("Own first-lag prior mean");
});
it("marks the active comparison and displays the likelihood grid to two decimals", () => {
  const grid = structuredClone(result);
  (grid.bvar as Record<string, unknown>).lambda_selection = "grid";
  (grid.bvar as Record<string, unknown>).grid = [
    { lambda: 0.2, log_marginal_likelihood: -812.471577, selected: true },
    { lambda: 0.3, log_marginal_likelihood: -813.112, selected: false },
  ];
  const html = renderToStaticMarkup(
    <BvarResults result={grid} manifest={manifest} />,
  );
  expect(html).toContain('class="primary" aria-pressed="true"');
  expect(html).toContain("-812.47");
  expect(html).toContain("-813.11");
  expect(html).toContain("Selected</td>");
  expect(html).not.toContain("true</td>");
  expect(html).not.toContain("false</td>");
});
