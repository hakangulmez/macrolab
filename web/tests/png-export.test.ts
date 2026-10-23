import { describe, expect, it } from "vitest";
import { buildVersion } from "../src/version";
import { exportText } from "../src/pngExport";
import { termLabel } from "../src/resultData";

describe("self-contained PNG metadata", () => {
  it("includes actual sample, pointwise level, active comparison and source disclaimer", () => {
    const text = exportText(
      [
        {
          name: "Real GDP",
          unit: "percentage points",
          summary: "",
          points: [
            { period: 0, value: 0, lower: -1, upper: 1, comparison: 0.2 },
          ],
        },
      ],
      {
        analysis: "Monetary policy",
        country: "United States",
        sample: "1999-Q3–2025-Q3 · n=105",
        frequency: "Q",
        sources: ["BIS", "EIA", "OECD"],
        bandLevel: 0.68,
        comparisonLabel: "Four lags",
        horizon: true,
      },
    );
    expect(text.title).toBe("Monetary policy · United States");
    expect(text.sample).toContain("n=105");
    expect(text.legend).toContain("68% pointwise interval");
    expect(text.legend).toContain("Four lags");
    expect(text.footer).toContain(
      `MacroLab ${buildVersion} · Data: BIS, EIA, OECD`,
    );
    expect(text.footer).toContain("Model scenario, not a forecast");
  });
  it("expands variable identifiers without altering numerical points", () => {
    expect(
      termLabel("L2.gdp_real", [{ concept_id: "gdp_real", title: "Real GDP" }]),
    ).toBe("Lag 2 · Real GDP");
    expect(termLabel("const", [])).toBe("Intercept");
  });
});
