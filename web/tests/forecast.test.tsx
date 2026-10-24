import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ForecastControls } from "../src/components/ForecastControls";
import { ForecastResults } from "../src/components/ForecastResults";
import { chartData, resultTableBlocks } from "../src/resultData";
import { exportText } from "../src/pngExport";
import { tableValue } from "../src/format";
import type { AnalysisConfig, CountryResult, Manifest } from "../src/types";
const manifest = {
  countries: [],
  indicators: [],
  templates: [],
} as unknown as Manifest;
const result = {
  country: "USA",
  model_id: "uni.arima",
  status: "ok",
  actual_sample: { transforms: {} },
  sensitivity: { variants: [] },
  forecast: {
    method: "SARIMAX",
    origin: "2025-Q3",
    variables: ["unemp"],
    units: { unemp: "%" },
    periods: ["2025-Q4", "2026-Q1"],
    history: { unemp: { periods: ["2025-Q3"], values: [4] } },
    distributions: {
      unemp: {
        mean: [4.1, 4.2],
        bands: {
          "0.68": { lower: [3.9, 3.8], upper: [4.3, 4.6] },
          "0.9": { lower: [3.6, 3.4], upper: [4.6, 5] },
        },
        inverse_method: "Analytic Gaussian linear inverse",
      },
    },
    assumptions: [
      "Final-vintage data; real-time performance may be worse.",
      "Future COVID dummies are zero.",
    ],
    interval_scope: "Conditional on fitted parameters",
  },
} as unknown as CountryResult;
it("keeps forecast units, both intervals and assumptions in export blocks", () => {
  const plots = chartData(result, []);
  expect(plots[0].points).toHaveLength(3);
  expect(plots[0].intervalLabel).toBe("90% predictive interval");
  expect(plots[0].unit).toBe("%");
  const blocks = resultTableBlocks(result);
  expect(blocks.some((b) => b.title.includes("68% predictive"))).toBe(true);
  expect(JSON.stringify(blocks)).toContain("Future COVID dummies are zero");
  const html = renderToStaticMarkup(
    <ForecastResults result={result} manifest={manifest} />,
  );
  expect(html).toContain("Predictive interval");
  expect(html).toContain("Final-vintage data");
  expect(html).toContain("Analytic Gaussian");
});
it("does not label a forecast PNG as an identified scenario", () => {
  const text = exportText(chartData(result, []), {
    forecast: true,
    analysis: "ARIMA",
    country: "United States",
    sample: "1999-Q1–2025-Q3",
    frequency: "Q",
    sources: ["OECD"],
    bandLevel: 0.9,
    comparisonLabel: "",
    horizon: false,
  });
  expect(text.footer).toContain("Forecast · final-vintage data");
  expect(text.footer).not.toContain("not a forecast");
  expect(text.legend).toContain("90% predictive interval");
});
it("exposes origin-local evaluation and explicit controls without introducing a template", () => {
  const config = {
    countries: ["USA"],
    frequency: "Q",
    model: { id: "fc.eval", params: {} },
    series: [{ concept_id: "unemp", role: "dependent", transform: "level" }],
  } as unknown as AnalysisConfig;
  const html = renderToStaticMarkup(
    <ForecastControls config={config} manifest={manifest} update={() => {}} />,
  );
  expect(html).toContain("40 quarters");
  expect(html).toContain("Not specified (blocks if exogenous series selected)");
  expect(html).toContain("orders at every origin");
  expect(tableValue("Forecast count", 67)).toBe("67");
  expect(tableValue("Horizon", 4)).toBe("4");
});

it("plots dated errors against the same-origin random walk and exports both sensitivities", async () => {
  const { forecastErrorChart } = await import("../src/resultData");
  const evaluation = {
    ...result,
    model_id: "fc.eval",
    forecast: undefined,
    evaluation: {
      target: "unemp",
      unit: "%",
      horizons: [1, 8],
      models: ["Random walk", "ARIMA"],
      metrics: [],
      dm_tests: [],
      origins: [],
      failed_origins: [],
      predictions: [
        {
          origin: "2020-Q2",
          target: "2022-Q2",
          horizon: 8,
          actual: 3.6,
          predictions: { ARIMA: 34.8, "Random walk": 13 },
        },
        {
          origin: "2020-Q2",
          target: "2020-Q3",
          horizon: 1,
          actual: 8.8,
          predictions: { ARIMA: 18.8, "Random walk": 13 },
        },
      ],
    },
    sensitivity: {
      variants: [
        {
          id: "exclude_2020_2021_targets",
          label: "Exclude 2020–2021 forecast targets",
          metrics: [],
        },
        {
          id: "exclude_2020_2021_origins",
          label: "Exclude forecasts made from 2020–2021 origins",
          metrics: [],
        },
      ],
    },
  } as unknown as CountryResult;
  const chart = forecastErrorChart(evaluation, "ARIMA", 8);
  expect(chart.unit).toBe("Percentage points");
  expect(chart.xAxisTitle).toBe("Forecast target date");
  expect(chart.points).toHaveLength(1);
  expect(chart.points[0].period).toBe("2022-Q2");
  expect(chart.points[0].value).toBeCloseTo(-31.2);
  expect(chart.points[0].comparison).toBeCloseTo(-9.4);
  const blocks = resultTableBlocks(evaluation);
  expect(
    blocks.find((b) => b.title.includes("Forecast errors by target"))?.rows,
  ).toHaveLength(4);
  const html = renderToStaticMarkup(
    <ForecastResults result={evaluation} manifest={manifest} />,
  );
  expect(html).toContain("Error model");
  expect(html).toContain("Exclude forecasts made from 2020–2021 origins");
  expect(html).toContain("Forecast error by target date");
});
