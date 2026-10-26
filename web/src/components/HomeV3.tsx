import { lazy, Suspense, useState } from "react";
import type { Manifest, Template } from "../types";
import {
  datasetCounts,
  methodFamilies,
  newInV2,
  templateCountries,
  templateTags,
} from "../uiData";
import { CoverageLegend, CoverageMatrix } from "./CoverageMatrix";
import { snapshotDate } from "../version";
const InflationHero = lazy(() => import("./InflationHero"));
export function Home({
  manifest,
  select,
  start,
  catalogue,
  models,
}: {
  manifest: Manifest;
  select: (t: Template) => void;
  start: () => void;
  catalogue: (selection?: {
    country?: string;
    search?: string;
    category?: string;
    region?: string;
  }) => void;
  models: () => void;
}) {
  const [filter, setFilter] = useState("All");
  const counts = datasetCounts(manifest);
  const family = (t: Template) =>
    t.config.model.id === "fc.eval"
      ? "Forecasting"
      : [
            "monetary_policy",
            "same_ecb_shock",
            "tur_pass_through",
            "same_ecb_shock_pooled",
          ].includes(t.id)
        ? "Shocks"
        : "Relationships";
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
    <section className="home-v3 stack" data-testid="screen-home">
      <div className="home-hero">
        <div className="hero-copy">
          <p className="overline">A browser-based macroeconomic lab</p>
          <h1>
            Explore the data.
            <br />
            Question the model.
          </h1>
          <p className="hero-description">
            Macroeconomic data and validated econometrics, with the assumptions
            in view. Start with a series, compare economies, or put a model to
            the test.
          </p>
          <div className="row hero-actions">
            <a className="button primary" href="#templates">
              Start an analysis <span aria-hidden="true">↓</span>
            </a>
            <button onClick={() => catalogue()}>Browse the dataset</button>
          </div>
          <p className="trust-line">
            No account · No analysis server
            <br />
            Every result exports to Python
          </p>
        </div>
        <Suspense
          fallback={
            <section className="card hero-chart-loading" role="status">
              Preparing the snapshot chart…
            </section>
          }
        >
          <InflationHero snapshot={manifest.snapshot_id} />
        </Suspense>
      </div>
      <dl className="stats-strip" aria-label="Dataset and method statistics">
        {[
          [counts.economies, "Economies"],
          [counts.indicators, "Indicators"],
          [counts.populated, "Populated series"],
          [counts.methods, "Validated methods"],
          [counts.templates, "Templates"],
          [0, "Analysis servers"],
        ].map(([n, l]) => (
          <div key={String(l)}>
            <dt>{l}</dt>
            <dd>{Number(n).toLocaleString("en")}</dd>
          </div>
        ))}
      </dl>
      <section className="section-v3" id="templates">
        <div className="section-heading">
          <div>
            <p className="overline">Templates</p>
            <h2>Start with a question.</h2>
            <p>
              <button className="link" onClick={start}>
                …or build your own analysis →
              </button>
            </p>
            <p>Run a reviewed specification. Then change the assumptions.</p>
          </div>
          <div className="category-tabs" aria-label="Filter templates">
            {["All", "Shocks", "Relationships", "Forecasting"].map((f) => (
              <button
                key={f}
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <div className="template-grid">
          {manifest.templates
            .filter((t) => filter === "All" || family(t) === filter)
            .map((t) => (
              <button
                key={t.id}
                data-testid={"template-" + t.id}
                className="template-card"
                onClick={() => select(t)}
              >
                <div className="template-top">
                  <span className="badge mono">{templateTags[t.id]}</span>
                  {newInV2.has(t.id) && (
                    <span className="new-badge">New in v2</span>
                  )}
                </div>
                <svg
                  className="template-pictogram"
                  viewBox="0 0 90 38"
                  aria-hidden="true"
                >
                  <path
                    d={
                      family(t) === "Shocks"
                        ? "M4 28H86M10 24L23 7L39 12L54 21L72 24L86 24"
                        : family(t) === "Forecasting"
                          ? "M4 24L17 18L31 22L45 13M45 13L86 4M45 13L86 31M45 13L86 17"
                          : "M4 29H86M16 6V24M10 6H22M10 24H22M43 10V29M37 10H49M37 29H49M70 3V20M64 3H76M64 20H76"
                    }
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                  />
                  <circle
                    cx={family(t) === "Relationships" ? 43 : 23}
                    cy={family(t) === "Relationships" ? 19 : 7}
                    r="3"
                    fill="currentColor"
                  />
                </svg>
                <h3>{t.title}</h3>
                <p>{t.description}</p>
                <span className="card-foot">
                  <span>
                    Default:{" "}
                    {templateCountries[t.id] ??
                      manifest.countries.find(
                        (c) => c.iso3 === t.config.countries[0],
                      )?.name}
                  </span>
                  <span aria-hidden="true">↗</span>
                </span>
              </button>
            ))}
        </div>
      </section>
      <section className="section-v3 dataset-preview">
        <div className="section-heading">
          <div>
            <p className="overline">The dataset, without the guesswork</p>
            <h2>Every economy. Every gap.</h2>
            <p>
              {counts.economies} economies × {counts.indicators} indicators (
              {counts.national} national + {counts.global} global factors).{" "}
              {counts.cells.toLocaleString("en")} cells;{" "}
              {counts.populated.toLocaleString("en")} populated,{" "}
              {counts.statuses.missing} missing.
            </p>
          </div>
          <button onClick={() => catalogue()}>Open dataset explorer ↗</button>
        </div>
        <div className="card">
          <CoverageLegend manifest={manifest} />
          <CoverageMatrix manifest={manifest} compact />
        </div>
        <p className="small muted">
          Data snapshot {snapshotDate(manifest.as_of_date)}. Shared global
          factors appear for each economy. Source definitions and limitations
          remain attached to every series.
        </p>
      </section>
      <section className="section-v3">
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
      <section className="source-strip">
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
    </section>
  );
}
