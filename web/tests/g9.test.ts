import { buildVersion, snapshotDate } from "../src/version";
import { expect, it } from "vitest";
import { chartData } from "../src/resultData";
import { exportText } from "../src/pngExport";
import type { CountryResult } from "../src/types";

it("NEER shows the same-fit normal 68% marginal band without changing ratio or CPI", () => {
  const input = {
    country: "TUR",
    status: "ok",
    actual_sample: { transforms: {} },
    irf: {
      variables: ["cpi"],
      periods: [0],
      values: [[0.5]],
      lower: [[0.3]],
      upper: [[0.7]],
      band_level: 0.68,
    },
    pass_through: {
      status: "ok",
      exchange_rate: "neer",
      secondary_label: "response to an initial 1% depreciation",
      horizons: [
        {
          horizon: 0,
          ratio: 0.25,
          fx_cumulative: -2,
          fx_std_error: 0.5,
          bands: { "0.68": { lower: 0.2, upper: 0.3 } },
        },
      ],
    },
  };
  const original = JSON.stringify(input);
  const charts = chartData(input as unknown as CountryResult, []);
  expect(charts[0].points[0]).toMatchObject({
    value: 0.25,
    lower: 0.2,
    upper: 0.3,
  });
  expect(charts[1].points[0]).toMatchObject({
    value: 0.5,
    lower: 0.3,
    upper: 0.7,
  });
  expect(charts[2].points[0].lower).toBeCloseTo(-2.497228941604877, 12);
  expect(charts[2].points[0].upper).toBeCloseTo(-1.502771058395123, 12);
  expect(JSON.stringify(input)).toBe(original);
});

it("CPI-only comparison is absent from the shared PNG legend", () => {
  const output = exportText(
    [
      {
        name: "CPI",
        unit: "%",
        summary: "",
        pngComparisonLabel: "2003 window",
        points: [{ period: 0, value: 1, comparison: 2 }],
      },
    ],
    {
      analysis: "Exchange-rate pass-through",
      country: "Türkiye",
      sample: "sample",
      frequency: "M",
      sources: ["BIS", "OECD"],
      bandLevel: 0.68,
      comparisonLabel: "2003 window",
      horizon: true,
    },
  );
  expect(output.title).toBe("Exchange-rate pass-through · Türkiye");
  expect(output.legend).not.toContain("2003");
});

it("release badge uses the build version and the selected data date", () => {
  expect(buildVersion).toBe("v1.0.1");
  expect(snapshotDate("2026-10-23")).toBe("23 Oct 2026");
});
