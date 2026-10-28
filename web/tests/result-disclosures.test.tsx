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
