import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DataTable } from "../src/components/Common";
import { Chart } from "../src/components/Chart";
import { ChartExportContext } from "../src/chartExportContext";
import {
  PanelResults,
  PanelCovarianceTable,
} from "../src/components/PanelResults";
import { reportedDF, coefficientStars, tTail } from "../src/coefficientDisplay";
import { horizonAxisTitle, tableValue } from "../src/format";
import { termLabel } from "../src/resultData";
import type { CountryResult, Manifest } from "../src/types";
import type { PngContext } from "../src/pngExport";

it("uses reported Student t uncertainty for display stars, including low and rank-deficient df", () => {
  // Independent scipy.stats.t reference values; no model calls or mutations.
  const reference = [
    [1, 12.706204736174694, 0.2951672353008665],
    [2, 4.302652729749462, 0.18350341907227394],
    [10, 2.228138851986274, 0.07338803477074037],
    [83, 1.9889597801751624, 0.04877055024436806],
    [101, 1.983731002955606, 0.0481852112073907],
    [1191, 1.961957807284942, 0.045727016347917405],
  ];
  for (const [df, critical, p] of reference) {
    expect(tTail(2, df)).toBeCloseTo(p, 11);
    expect(tTail(-2, df)).toBeCloseTo(p, 11);
    const row = {
      estimate: 2,
      std_error: 1,
      lower: 2 - critical,
      upper: 2 + critical,
      confidence_level: 0.95,
    };
    const before = JSON.stringify(row);
    expect(reportedDF(row, df + 30)).toBe(df);
    expect(coefficientStars(row, df)).toBe(
      df <= 2 ? "" : df === 10 ? "*" : "**",
    );
    expect(JSON.stringify(row)).toBe(before);
  }
  expect(coefficientStars({ estimate: 3, std_error: 1 }, 83)).toBe("***");
  expect(coefficientStars({ estimate: 0, std_error: 1 }, 83)).toBe("");
  expect(reportedDF({ std_error: 0 }, 100)).toBeUndefined();
});

it("keeps all country columns and integer fields, while estimates retain three significant figures", () => {
  const rows = [
    {
      Term: "Oil",
      ...Object.fromEntries(
        Array.from({ length: 11 }, (_, i) => [`Country ${i}`, i + 0.123]),
      ),
    },
  ];
  const html = renderToStaticMarkup(<DataTable rows={rows} stickyFirst />);
  expect(html.match(/scope="col"/g)).toHaveLength(12);
  expect(html).toContain("Country 10");
  expect(html).toContain("Scroll horizontally");
  for (const key of [
    "Horizon",
    "Peak horizon",
    "period",
    "Observations",
    "common_nobs",
    "actual_sample_nobs",
    "residual_degrees_of_freedom",
    "parameter_count_per_equation",
    "adf_lags",
    "T_min",
    "N",
    "df_resid",
    "dk_bandwidth",
    "draws",
    "lag",
    "seed",
    "year",
  ])
    expect(tableValue(key, 20)).toBe("20");
  expect(tableValue("Estimate", 20)).toBe("20.0");
  expect(tableValue("std_error", 1)).toBe("1.00");
});

it("states FE uncertainty, collapses only COVID rows, and orders covariance columns", () => {
  const row = {
    term: "oil_brent",
    estimate: 0.012390218053531398,
    std_error: 0.005817221347406237,
    lower: 0.0009770752142831025,
    upper: 0.023803360892779693,
    confidence_level: 0.95,
    covariance: "Driscoll-Kraay",
  };
  const covid = Array.from({ length: 6 }, (_, i) => ({
    ...row,
    term: `covid_${2020 + Math.floor(i / 4)}-Q${(i % 4) + 1}`,
  }));
  const r = {
    country: "POOLED",
    model_id: "panel.fe",
    status: "ok",
    checks: [],
    coefficients_table: [row, ...covid],
    actual_sample: { transforms: {} },
    sensitivity: {
      variants: [{ label: "conventional", rows: [row, ...covid] }],
    },
    panel: {
      df_resid: 1191,
      covariance: "Driscoll-Kraay",
      country_samples: { DEU: { nobs: 1200 } },
      country_estimates: { DEU: [row, ...covid] },
    },
  } as unknown as CountryResult;
  const manifest = {
    countries: [{ iso3: "DEU", name: "Germany" }],
    indicators: [{ concept_id: "oil_brent", title: "Oil" }],
  } as Manifest;
  const before = JSON.stringify(r);
  const html = renderToStaticMarkup(
    <PanelResults result={r} manifest={manifest} />,
  );
  const main = html.split("</table>")[0];
  expect(main).toContain("Pooled: Driscoll-Kraay; country OLS: HAC(4)");
  expect(main).toContain("(0.00582)");
  expect(main).toContain("<sup>**</sup>");
  expect(main).toContain('aria-expanded="false"');
  expect(main).toContain("COVID dummies (6)");
  expect(main).not.toContain("COVID dummy 2020 Q1");
  expect(html).toContain("COVID dummy 2020 Q1");
  expect(html).toContain(
    "95% confidence intervals (Conventional standard errors)",
  );
  expect(html).toContain(
    '<th scope="col">Term</th><th scope="col">Estimate</th><th scope="col">Std. error</th><th scope="col">Lower</th><th scope="col">Upper</th>',
  );
  expect(JSON.stringify(r)).toBe(before);
});

it("uses readable terms and shared time-axis titles for browser and PNG responses", () => {
  expect(termLabel("covid_2020-Q1", [])).toBe("COVID dummy 2020 Q1");
  expect(
    termLabel("oil_brent", [
      { concept_id: "oil_brent", title: "Brent USD/bbl" },
    ]),
  ).toBe("Brent oil price");
  for (const [frequency, label] of [
    ["Q", "Quarters"],
    ["M", "Months"],
  ]) {
    const axis = `${label} after the shock`;
    expect(horizonAxisTitle(frequency)).toBe(axis);
    const html = renderToStaticMarkup(
      <ChartExportContext.Provider
        value={{ frequency, horizon: true } as PngContext}
      >
        <Chart
          estimateLabel="Response"
          comparisonShortLabel=""
          title="Response"
          unit="%"
          summary="Test"
          points={[{ period: 0, value: 1 }]}
        />
      </ChartExportContext.Provider>,
    );
    expect(html).toContain(`data-x-axis-title="${axis}"`);
  }
});

it("uses the identical five-column LP sensitivity view in main and technical details", () => {
  const rows = [
    { horizon: 0, estimate: 1, std_error: 0.2 },
    { horizon: 20, estimate: 2, std_error: 0.1 },
  ];
  const before = JSON.stringify(rows);
  const html = renderToStaticMarkup(
    <PanelCovarianceTable
      rows={rows}
      label="country-clustered"
      lp
      indicators={[]}
    />,
  );
  expect(html).toContain("90% pointwise intervals (country-clustered)");
  expect(html).toContain(
    '<th scope="col">Horizon</th><th scope="col">Estimate</th><th scope="col">Std. error</th><th scope="col">Lower</th><th scope="col">Upper</th>',
  );
  expect(html).toContain(
    "<td>0</td><td>1.00</td><td>0.200</td><td>0.671</td><td>1.33</td>",
  );
  expect(html).toContain("<td>20</td>");
  expect(JSON.stringify(rows)).toBe(before);
});
