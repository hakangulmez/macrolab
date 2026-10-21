import { describe, expect, it } from "vitest";
import { indicatorSummary, number } from "../src/format";
import type { Manifest } from "../src/types";

describe("scientific values remain distinguishable from zero", () => {
  it("preserves a small test p-value and a negative log response", () => {
    expect(Number(number(2.5e-8, 6))).toBeCloseTo(2.5e-8, 12);
    expect(Number(number(-0.00037, 2))).toBeCloseTo(-0.00037, 10);
    expect(number(0, 6)).toBe("0");
  });
});

describe("catalogue counts reflect the candidate metadata", () => {
  const fixture = {
    indicators: [
      ...Array.from({ length: 33 }, (_, index) => ({
        concept_id: `national_${index}`,
        scope: "national",
        title: "National",
      })),
      ...["oil_brent", "us_policy_rate", "commod_idx"].map((concept_id) => ({
        concept_id,
        scope: "global",
        title: concept_id,
      })),
    ],
  } as Manifest;
  it("distinguishes included factors from visible excluded metadata", () => {
    expect(indicatorSummary(fixture)).toBe("33 indicators + 3 global factors");
    const candidate = {
      ...fixture,
      publication: { included_global_factors: ["oil_brent", "us_policy_rate"] },
    } as Manifest;
    expect(indicatorSummary(candidate)).toBe(
      "33 indicators + 2 included global factors",
    );
    expect(
      indicatorSummary({
        ...candidate,
        publication: { ...candidate.publication!, source_mode: "all" },
      }),
    ).toBe("33 indicators + 3 global factors");
  });
});
