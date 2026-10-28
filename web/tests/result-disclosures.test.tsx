import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { ResultDataTable } from "../src/components/ResultDataTable";

it("keeps short summaries inline and preserves every long-table row unchanged", () => {
  const short = [
    { term: "Intercept", estimate: 0.123456789 },
    { term: "Unemployment", estimate: -0.65 },
  ];
  const long = Array.from({ length: 21 }, (_, horizon) => ({
    horizon,
    estimate: horizon / 7,
  }));
  const before = structuredClone(long);
  expect(renderToStaticMarkup(<ResultDataTable rows={short} />)).not.toContain(
    "<details",
  );
  const html = renderToStaticMarkup(
    <ResultDataTable rows={long} caption="Full impulse responses" />,
  );
  expect(html).toContain(
    '<details class="result-table-disclosure"><summary>Full impulse responses</summary>',
  );
  expect(html).not.toContain(" open");
  expect(html.match(/<tr>/g)).toHaveLength(22);
  expect(html).toContain(">20<");
  expect(long).toEqual(before);
});

it("collapses wide matrices and explicitly detailed tables without dropping columns", () => {
  const row = Object.fromEntries(
    Array.from({ length: 11 }, (_, i) => [`Country ${i}`, i / 3]),
  );
  const html = renderToStaticMarkup(<ResultDataTable rows={[row]} />);
  expect(html).toContain("<summary>Full result table</summary>");
  expect(html.match(/scope="col"/g)).toHaveLength(11);
  expect(
    renderToStaticMarkup(
      <ResultDataTable
        rows={[{ horizon: 0 }]}
        detailsLabel="Detailed sensitivity estimates"
      />,
    ),
  ).toContain("<summary>Detailed sensitivity estimates</summary>");
});

it("keeps a primary test table exposed even when it has many critical-value columns", () => {
  const rows = [
    {
      rank: 0,
      trace: 32,
      c90: 10,
      c95: 12,
      c99: 18,
      maximum: 24,
      m90: 8,
      m95: 10,
      m99: 15,
    },
  ];
  const original = structuredClone(rows);
  const html = renderToStaticMarkup(<ResultDataTable primary rows={rows} />);
  expect(html).not.toContain("<details");
  expect(html.match(/scope="col"/g)).toHaveLength(9);
  expect(rows).toEqual(original);
});
