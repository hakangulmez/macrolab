import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DataTable } from "../src/components/Common";
import { significant } from "../src/format";
import { analysisCsvRows } from "../src/resultData";

describe("v1.0.1 display precision", () => {
  it("exports every analysis check verbatim even when displayed as one finding", () => {
    const checks = [0, 1, 2].map((horizon) => ({
      code: "small_sample",
      level: "warn",
      message: "Same finding",
      country: "DEU",
      horizon,
      observations_per_parameter: 3.680123456789,
    }));
    const rows = analysisCsvRows({
      results: [],
      checks,
      snapshot_id: "frozen",
      config_hash: "hash",
    });
    expect(rows).toEqual(
      checks.map((check) => ({
        record_type: "analysis_check",
        ...check,
        snapshot: "frozen",
        config_hash: "hash",
      })),
    );
  });
  it("uses three significant figures, including small values, without scientific notation", () => {
    expect([0.30261, -0.000648123, 12.345, 0, 1].map(significant)).toEqual([
      "0.303",
      "-0.000648",
      "12.3",
      "0.00",
      "1.00",
    ]);
  });
  it("shows full country names and integer counts without changing input rows", () => {
    const rows = [
      {
        Country: "DEU",
        Observations: 92,
        "Peak horizon": 1,
        Estimate: 0.30261,
      },
    ];
    const original = JSON.stringify(rows);
    const html = renderToStaticMarkup(
      <DataTable rows={rows} countries={[{ iso3: "DEU", name: "Germany" }]} />,
    );
    expect(html).toContain("Germany");
    expect(html).not.toContain("DEU");
    expect(html).toContain("<td>92</td>");
    expect(html).toContain("<td>1</td>");
    expect(html).toContain("<td>0.303</td>");
    expect(JSON.stringify(rows)).toBe(original);
  });
});
