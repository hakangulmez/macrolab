import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ResultDataTable } from "../src/components/ResultDataTable";
import {
  baselineResultChecks,
  resultTableColumns,
} from "../src/resultPresentation";
import type { AnalysisResult } from "../src/types";
import type { Manifest } from "../src/types";
import fixture from "./fixtures/result-layers.json";
import { Results } from "../src/components/Results";

describe("research result presentation", () => {
  it("shows one complete key-number summary for results without Key facts", () => {
    const result = structuredClone(
      fixture.results.phillips_curve,
    ) as unknown as AnalysisResult;
    result.config.model.id = "sing.ardl";
    result.results.forEach((country) => {
      country.checks = [];
      country.actual_sample.transforms = {};
      country.actual_sample.frequency_conversion = {};
      country.actual_sample.dropped_periods = [];
      country.actual_sample.common_nobs = country.actual_sample.nobs;
    });
    const html = renderToStaticMarkup(
      <Results
        result={result}
        manifest={fixture.manifest as unknown as Manifest}
        bundles={{}}
        busy={false}
        rerun={() => {}}
        exportPython={() => {}}
        share={() => {}}
        shareUrl=""
        edit={() => {}}
      />,
    );
    expect(html.match(/class="result-kpis"/g)).toHaveLength(1);
    expect(html).toContain("<dt>Standard error</dt>");
    expect(html).toContain("<dt>Reported interval</dt>");
    expect(html).toContain("<dt>Observations</dt>");
  });
  it("keeps coefficient identifiers first, bounds adjacent, and every supplied field", () => {
    const rows = [
      {
        estimate: -0.65,
        lower: -1.12,
        p_value: 0.00724,
        std_error: 0.238,
        term: "unemp",
        upper: -0.179,
        extra: "retained",
      },
    ];
    const before = JSON.stringify(rows);
    expect(resultTableColumns(rows)).toEqual([
      "term",
      "estimate",
      "std_error",
      "lower",
      "upper",
      "p_value",
      "extra",
    ]);
    expect(JSON.stringify(rows)).toBe(before);
  });
  it("gives short coefficient records readable mobile labels without losing precision or values", () => {
    const html = renderToStaticMarkup(
      <ResultDataTable
        rows={[
          {
            term: "unemp",
            estimate: -0.65,
            std_error: 0.238,
            lower: -1.12,
            upper: -0.179,
            p_value: 0.00724,
          },
        ]}
      />,
    );
    expect(html).toContain("mobile-records");
    expect(html).toMatch(/<th[^>]*>Variable<\/th><th[^>]*>Estimate<\/th>/);
    expect(html).toContain('data-label="p-value"');
    for (const v of ["unemp", "-0.650", "0.238", "-1.12", "-0.179", "0.00724"])
      expect(html).toContain(`>${v}</td>`);
    expect(html.match(/<td /g)).toHaveLength(6);
  });
  it("preserves an explicit matrix schema and its complete set of columns", () => {
    const columns = ["Term", "Pooled", "Germany", "France", "Italy", "Spain"];
    expect(
      resultTableColumns(
        [
          {
            Term: "Policy rate",
            Pooled: 1,
            Germany: 2,
            France: 3,
            Italy: 4,
            Spain: 5,
          },
        ],
        columns,
      ),
    ).toEqual(columns);
  });
  it("keeps primary test tables visible even when long", () => {
    const html = renderToStaticMarkup(
      <ResultDataTable
        primary
        rows={Array.from({ length: 15 }, (_, i) => ({
          test: `test ${i}`,
          statistic: i,
          p_value: i / 100,
        }))}
      />,
    );
    expect(html).not.toContain("<details");
    expect(html.match(/<tr>/g)).toHaveLength(16);
  });
  it("unifies identical baseline records while preserving severity, phase and country scope", () => {
    const check = {
      level: "warn",
      code: "small_sample",
      message: "Sample is small",
      country: "CAN",
      phase: "post_estimation",
    };
    const result = {
      checks: [check],
      results: [
        { country: "CAN", checks: [check, { ...check, level: "block" }] },
        { country: "GBR", checks: [{ ...check, country: "GBR" }] },
      ],
    } as unknown as AnalysisResult;
    const before = JSON.stringify(result);
    const checks = baselineResultChecks(result);
    expect(checks).toHaveLength(3);
    expect(
      checks.filter((c) => c.country === "CAN").map((c) => c.level),
    ).toEqual(["warn", "block"]);
    expect(checks.find((c) => c.country === "GBR")?.phase).toBe(
      "post_estimation",
    );
    expect(JSON.stringify(result)).toBe(before);
  });
});
