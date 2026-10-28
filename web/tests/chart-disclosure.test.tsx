import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { Chart } from "../src/components/Chart";

it("collapses only per-point chart data while preserving rows, controls and exports", () => {
  const points = Array.from({ length: 111 }, (_, period) => ({
    period,
    value: period / 7,
    comparison: period / 11,
  }));
  const before = structuredClone(points);
  const html = renderToStaticMarkup(
    <Chart
      title="Observed and fitted"
      unit="% y/y"
      points={points}
      summary="Existing observations and fitted values."
      estimateLabel="Observed"
      comparisonShortLabel="Fitted"
      controls={<button>Choose series</button>}
      exportContext={{
        analysis: "Phillips curve",
        country: "Canada",
        sample: "111 observations",
        frequency: "Q",
        sources: [],
        bandLevel: 0.95,
        comparisonLabel: "Fitted",
        horizon: false,
      }}
    />,
  );
  const start = html.indexOf('<details class="chart-values">');
  expect(start).toBeGreaterThan(0);
  expect(html).toContain(
    '<details class="chart-values"><summary>Show chart data</summary>',
  );
  expect(html).not.toContain('<details class="chart-values" open');
  expect(html.slice(0, start)).toContain('role="img"');
  expect(html.slice(0, start)).toContain("Choose series");
  expect(html.slice(0, start)).toContain('aria-label="Export PNG:');
  const rows = html.split("<tbody>")[1].split("</tbody>")[0];
  expect(rows.match(/<tr>/g)).toHaveLength(111);
  expect(rows).toContain(">110<");
  expect(points).toEqual(before);
});
