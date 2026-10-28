import { createElement } from "react";
import type { AnalysisResult, Manifest } from "../types";
import { resultSpecification } from "../resultSpecification";
export function ResultSpecification({
  result,
  manifest,
}: {
  result: AnalysisResult;
  manifest: Manifest;
}) {
  const spec = resultSpecification(result, manifest);
  return (
    <section
      className="card stack specification-box"
      data-testid="specification-box"
    >
      <h2>Econometric specification</h2>
      <div
        className="equation-scroll"
        tabIndex={0}
        role="region"
        aria-label="Estimated equation"
      >
        {createElement(
          "math",
          { display: "block", "aria-label": spec.equation },
          createElement(
            "mrow",
            null,
            ...spec.equation
              .split(/( = | \+ | − )/)
              .map((token, i) =>
                createElement(
                  /^( = | \+ | − )$/.test(token) ? "mo" : "mtext",
                  { key: i },
                  token,
                ),
              ),
          ),
        )}
      </div>
      {spec.definitions.map((line) => (
        <p className="small" key={line}>
          {line}
        </p>
      ))}
      <p className="small mono">{spec.settings}</p>
    </section>
  );
}
