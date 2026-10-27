import type { Manifest } from "../types";
import { datasetCounts, methodFamilies } from "../uiData";

export function AboutSections({
  manifest,
  models,
}: {
  manifest: Manifest;
  models: () => void;
}) {
  const counts = datasetCounts(manifest);
  const sources = [
    ...new Set(
      manifest.sources
        .map((s) => String(s.name))
        .filter((s) => !["FRED", "World Bank Pink Sheet"].includes(s))
        .map((s) =>
          s.startsWith("IMF") ? "IMF" : s.startsWith("U.S.") ? "U.S. EIA" : s,
        ),
    ),
  ];
  return (
    <>
      <section className="section-v3" id="method-families">
        <div className="section-heading">
          <div>
            <p className="overline">Methods, with their assumptions</p>
            <h2>{counts.methods} validated methods.</h2>
          </div>
          <button className="link" onClick={models}>
            Explore the model library ↗
          </button>
        </div>
        <div className="method-family-grid">
          {methodFamilies.map((f) => (
            <button key={f.name} onClick={models}>
              <span className="mono">
                {manifest.models
                  .filter((m) => f.ids.includes(m.id))
                  .length.toString()
                  .padStart(2, "0")}
              </span>
              <strong>{f.name}</strong>
              <small>
                {manifest.models
                  .filter((m) => f.ids.includes(m.id))
                  .map((m) => m.title)
                  .join(" · ")}
              </small>
              <span aria-hidden="true">↗</span>
            </button>
          ))}
        </div>
      </section>
      <section className="source-strip" id="official-sources">
        <p className="overline">Official sources. Visible limits.</p>
        <div>
          {sources.map((s) => (
            <span key={s}>{s}</span>
          ))}
        </div>
        <p className="small muted">
          Every series carries attribution and a coverage record. Data terms
          differ by source. Missing data stay missing.
        </p>
      </section>
    </>
  );
}
