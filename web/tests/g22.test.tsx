import { expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { analysisErrorMessage, errorControl } from "../src/analysisErrors";
import { chartDisplay, resultDisplayLabel } from "../src/chartDisplay";
import { Chart } from "../src/components/Chart";
import type { CountryResult } from "../src/types";
import type { ResultChart } from "../src/resultData";
it("extracts actionable validation messages, never Python traceback frames", () => {
  for (const exception of ["ConfigError", "ValidationError", "ValueError"]) {
    expect(
      analysisErrorMessage(
        new Error(
          `PythonError: Traceback (most recent call last):\n  File "/lib/python.zip", line 9\nmacrolab.config.${exception}: Specify an explicit recursive ordering`,
        ),
      ),
    ).toBe("Specify an explicit recursive ordering");
  }
  expect(
    analysisErrorMessage(
      'Traceback (most recent call last):\n  File "/lib/python.zip", line 3',
    ),
  ).not.toMatch(/Traceback|\/lib/);
  expect(analysisErrorMessage(new Error("Cancelled"))).toBe("Cancelled");
  expect(
    errorControl("Specify an explicit recursive ordering", "out.hd").id,
  ).toBe("identification-control");
  expect(
    errorControl("Specify an explicit recursive ordering", "cmp.common_shock")
      .id,
  ).toBe("first-stage-config");
});
it("assigns meaningful labels without mutating results or export-facing fields", () => {
  for (const [model_id, name, estimate, comparison] of [
    ["sing.ols", "CPI: observed and fitted", "Observed", "Fitted"],
    ["sing.ardl", "CPI: residual", "Residual", "Fitted"],
    ["filter.hp", "CPI: observed and trend", "Observed", "Trend"],
    ["filter.hamilton", "CPI: cycle", "Cycle", "Trend"],
    ["var.ols", "CPI", "Baseline", "Reversed order"],
    ["ident.recursive", "GDP", "Baseline", "Reversed order"],
    ["desc.plot", "CPI", "Observed", ""],
    ["desc.corr", "Rolling correlation", "Correlation", ""],
    ["lp.ols", "GDP", "Response", ""],
  ]) {
    const result = { model_id } as CountryResult;
    const chart: ResultChart = {
      name,
      unit: "%",
      points: [{ period: 0, value: 1 }],
      summary: "Source text",
    };
    const before = JSON.stringify({ result, chart }),
      labels = chartDisplay(result, chart, []);
    expect([labels.estimateLabel, labels.comparisonShortLabel]).toEqual([
      estimate,
      comparison,
    ]);
    expect(JSON.stringify({ result, chart })).toBe(before);
  }
  const source = readFileSync(
    new URL("../src/components/Chart.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toContain("estimateLabel: string");
  expect(source).toContain("comparisonShortLabel: string");
  expect(source).not.toMatch(
    /(?:estimateLabel|comparisonShortLabel)\s*=\s*["'](?:Estimate|Comparison)/,
  );
  expect(
    source.match(/labelLayout: \{ moveOverlap: "shiftY" \}/g),
  ).toHaveLength(2);
});
it("adds a two-line legend and corrects only visible captions", () => {
  const html = renderToStaticMarkup(
    <Chart
      title="Observed and fitted"
      unit="%"
      points={[{ period: 1, value: 2, comparison: 2 }]}
      summary="Original caption"
      displaySummary="Readable caption"
      estimateLabel="Observed"
      comparisonShortLabel="Fitted"
    />,
  );
  expect(html).toContain('aria-label="Chart series"');
  expect(html).toContain("Fitted");
  expect(html).toContain("Readable caption");
  expect(
    resultDisplayLabel(
      "Conditional association to a -1-unit move in neer, controlling for lags",
    ),
  ).toBe(
    "Conditional association to a 1% depreciation (fall in NEER), controlling for lags",
  );
  expect(resultDisplayLabel("Other result label")).toBe("Other result label");
  expect(
    chartDisplay(
      { model_id: "test.adf_kpss_pp" } as CountryResult,
      {
        name: "ADF",
        summary: "unit root Test p-values",
        unit: "p",
        points: [],
      },
      [],
    ).displaySummary,
  ).toBe("Null hypothesis: unit root. Test p-values");
});
