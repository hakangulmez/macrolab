import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import fixture from "./fixtures/result-layers.json";
import expected from "./fixtures/result-layers-expected.json";
import { keyFacts, robustnessHeadlines } from "../src/resultFacts";
import { resultSpecification } from "../src/resultSpecification";
import { ResultSpecification } from "../src/components/ResultSpecification";
import type { AnalysisResult, Manifest } from "../src/types";
const manifest = fixture.manifest as unknown as Manifest;
const results = fixture.results as unknown as Record<
  keyof typeof expected,
  AnalysisResult
>;
for (const id of Object.keys(expected) as (keyof typeof expected)[]) {
  it(`${id}: all fixed Key facts sentences retain the accepted returned numbers and actual sample`, () => {
    const before = JSON.stringify(results[id]);
    expect(keyFacts(results[id], manifest)).toEqual(expected[id].facts);
    expect(JSON.stringify(results[id])).toBe(before);
  });
  it(`${id}: native MathML carries the actual equation and variable names`, () => {
    expect(resultSpecification(results[id], manifest)).toEqual({
      equation: expected[id].equation,
      definitions: expected[id].definitions,
      settings: expected[id].settings,
    });
    const html = renderToStaticMarkup(
      <ResultSpecification result={results[id]} manifest={manifest} />,
    );
    expect(html).toContain('<math display="block"');
    expect(html).toContain(
      `aria-label="${expected[id].equation.replaceAll("&", "&amp;").replaceAll('"', "&quot;")}"`,
    );
    expect(html).toContain('tabindex="0"');
  });
}
it("custom Builder results fall back to key-number cards", () => {
  const result = structuredClone(results.phillips_curve);
  result.config.model.id = "sing.ardl";
  expect(keyFacts(result, manifest)).toEqual([]);
});
it("sign/range headlines use returned summary fields without deriving material flags", () => {
  const result = structuredClone(results.same_ecb_shock);
  const before = JSON.stringify(result);
  expect(robustnessHeadlines(result, manifest)).toEqual([
    {
      line: "Same sign in 3 of 4 alternatives · selected-peak range -0.800 to 0.579",
      scope:
        "Germany · Real GDP (volume, SA) · sign at horizon 9; range of selected peaks.",
    },
  ]);
  expect(JSON.stringify(result)).toBe(before);
});
it("flag counts use only existing boolean flags, with different estimands excluded", () => {
  const result = structuredClone(results.ea_phillips_pooled);
  result.template_sensitivity = [
    {
      comparison: [
        { term: "unemp", material: false },
        { term: "oil_brent", material: true },
      ],
    },
    { same_estimand: false, comparison: [{ term: "unemp", material: false }] },
    {
      include_in_agreement_counts: false,
      comparison: [{ term: "unemp", material: false }],
    },
    { comparison: [{ term: "unemp", estimate: 99 }] },
  ];
  const before = JSON.stringify(result);
  expect(robustnessHeadlines(result, manifest)[0].line).toBe(
    "1 of 2 checks hold",
  );
  expect(JSON.stringify(result)).toBe(before);
});
it("the equation retains automatically required seasonal controls for NSA prices", () => {
  for (const id of [
    "tur_pass_through",
    "same_ecb_shock",
    "same_ecb_shock_pooled",
  ] as const) {
    const spec = resultSpecification(results[id], manifest);
    expect(spec.equation).toContain("s′ Sₜ");
    expect(spec.definitions.join()).toContain("calendar seasonality controls");
  }
});
