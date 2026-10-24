import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { Chart } from "../src/components/Chart";
import { ChartExportContext } from "../src/chartExportContext";
import { exportText } from "../src/pngExport";

const context = {
  analysis: "Historical decomposition",
  country: "United States",
  sample: "1999–2025; n=107",
  snapshot: "20261023-1634",
  frequency: "Q",
  sources: ["OECD", "BIS", "EIA"],
  bandLevel: 0.68,
  comparisonLabel: "Comparison",
  horizon: false,
};
it("gives each chart a PNG action whose accessible name contains its visible name", () => {
  const html = renderToStaticMarkup(
    <ChartExportContext.Provider value={context}>
      <Chart
        title="GDP contributions"
        unit="Annualised q/q growth"
        points={[{ period: "2020-Q1", value: -1 }]}
        summary="Accounting, not causal attribution"
        stack={[{ name: "Policy shock", color: "#0e7490", values: [-0.5] }]}
      />
    </ChartExportContext.Provider>,
  );
  expect(html).toContain('aria-label="Export PNG: GDP contributions"');
  expect(html).toContain(">Export PNG</button>");
  expect(html).toContain("Policy shock");
});
it("carries the frozen snapshot and sources into a per-chart export", () => {
  const labels = exportText(
    [{ name: "GDP", points: [], unit: "%", summary: "" }],
    context,
  );
  expect(labels.footer).toContain("Snapshot 20261023-1634");
  expect(labels.footer).toContain("Data: OECD, BIS, EIA");
});
