import { useState } from "react";
import type { AnalysisConfig, Manifest, Model, Template } from "../types";
import { indicatorSummary, record, records, text } from "../format";
export function Home({
  manifest,
  select,
  start,
  catalogue,
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
}) {
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const countries = manifest.countries.filter((c) =>
    `${c.name} ${c.iso3}`.toLowerCase().includes(query),
  );
  const indicators = manifest.indicators.filter((c) =>
    `${c.title} ${c.concept_id}`.toLowerCase().includes(query),
  );
  const categories = [
    ...new Set(manifest.indicators.map((c) => c.category ?? "Indicators")),
  ];
  return (
    <section data-testid="screen-home" className="stack">
      <div className="hero stack">
        <span className="overline">
          {manifest.countries.filter((c) => c.group === "member").length} OECD
          economies · euro area · {indicatorSummary(manifest)}
        </span>
        <h1>Explore, model and stress-test macro data across countries.</h1>
        <p>
          Start with a question. Choose your data and assumptions. See the
          estimate—and how much it changes with the model.
        </p>
        <div className="searchbar">
          <input
            aria-label="Search countries or indicators"
            type="search"
            placeholder="Search a country or indicator, e.g. Germany, core inflation"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="primary" onClick={start}>
            Start an analysis →
          </button>
        </div>
        {query && (
          <div className="card search-results">
            <strong>Matching data</strong>
            {countries.slice(0, 4).map((c) => (
              <button
                key={c.iso3}
                onClick={() => catalogue({ country: c.iso3 })}
              >
                {c.name}{" "}
                <span className="muted">
                  {c.iso3} · {c.region}
                </span>
              </button>
            ))}
            {indicators.slice(0, 4).map((i) => (
              <button
                key={i.concept_id}
                onClick={() => catalogue({ search: i.concept_id })}
              >
                {i.title} <span className="muted">{i.concept_id}</span>
              </button>
            ))}
            {!countries.length && !indicators.length && (
              <p>No matching country or indicator.</p>
            )}
          </div>
        )}
      </div>
      <section className="stack section">
        <div className="row between">
          <h2>Start from a template</h2>
          <span className="small muted">
            Working examples. Change every assumption.
          </span>
        </div>
        <div className="template-grid">
          {manifest.templates.map((t) => (
            <button
              data-testid={`template-${t.id}`}
              key={t.id}
              className="template-card"
              onClick={() => select(t)}
            >
              <span className="badge mono">
                {t.new_in_v1
                  ? "NEW · LP · HC1"
                  : t.config.model.id === "var.ols"
                    ? "VAR · recursive"
                    : t.id === "phillips_curve"
                      ? "OLS · rolling"
                      : "OLS · HAC"}
              </span>
              <h3>{t.title}</h3>
              <p>{t.description}</p>
              <span className="card-foot">
                <span>
                  Default:{" "}
                  {manifest.countries.find(
                    (c) => c.iso3 === t.config.countries[0],
                  )?.name ?? t.config.countries[0]}
                </span>
                <span aria-hidden="true">↗</span>
              </span>
            </button>
          ))}
        </div>
      </section>
      <section className="overview-grid section">
        <div className="card stack">
          <h3>Countries, in context</h3>
          <div className="link-grid">
            {[
              ...new Set(
                manifest.countries.map((c) => c.region ?? "Euro area"),
              ),
            ].map((r) => (
              <button key={r} onClick={() => catalogue({ region: r })}>
                {r}
              </button>
            ))}
          </div>
          <p className="small muted">
            Euro members share the ECB policy rate. National outcomes and
            adoption dates remain explicit.
          </p>
        </div>
        <div className="card stack">
          <h3>A coherent indicator catalogue</h3>
          <div className="link-grid">
            {categories.map((c) => (
              <button key={c} onClick={() => catalogue({ category: c })}>
                {c}{" "}
                <span className="mono">
                  {
                    manifest.indicators.filter(
                      (i) =>
                        (i.category ?? "Indicators") === c &&
                        record(i.publication).included !== false,
                    ).length
                  }
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="card stack">
          <h3>Official sources. Visible limits.</h3>
          <div className="row">
            {manifest.sources
              .filter((s) => s.name !== "FRED")
              .map((s) => (
                <span key={text(s.name)} className="badge draft mono">
                  {text(s.name)}
                </span>
              ))}
          </div>
          <p className="small muted">
            Every series carries units, coverage, attribution and source
            caveats. Missing data stay missing. FRED is unavailable.
          </p>
          <button onClick={() => catalogue()}>Explore the data →</button>
        </div>
      </section>
    </section>
  );
}
export function Library({
  manifest,
  compatibility,
  check,
  busy,
  selectModel,
  config,
}: {
  manifest: Manifest;
  compatibility: Model[] | null;
  check: () => void;
  busy: boolean;
  selectModel: (m: Model) => void;
  config: AnalysisConfig;
}) {
  const [family, setFamily] = useState("All");
  const models = compatibility ?? manifest.models;
  const families = ["All", ...new Set(models.map((m) => m.family))];
  return (
    <section data-testid="screen-library" className="stack">
      <div className="page-heading">
        <span className="overline">Model library · validated methods</span>
        <h1>A method for the question you’re asking.</h1>
        <p>
          Inspect assumptions before choosing. Compatibility is checked against
          your current countries, roles, transformations and actual data.
        </p>
      </div>
      <div className="row between">
        <div className="category-tabs">
          {families.map((f) => (
            <button
              key={f}
              aria-pressed={family === f}
              onClick={() => setFamily(f)}
            >
              {f.replaceAll("_", " ")}
            </button>
          ))}
        </div>
        <button disabled={busy} onClick={check}>
          Check current selection
        </button>
      </div>
      <p className="small muted">
        Current selection: {config.countries.join(", ")} ·{" "}
        {config.series.length} series · {config.frequency}.{" "}
        {compatibility
          ? "Compatibility checked."
          : "Check compatibility before switching methods."}
      </p>
      <div className="model-grid">
        {models
          .filter((m) => family === "All" || m.family === family)
          .map((m) => {
            const checks = m.checks ?? [];
            const blocked = checks.some((c) => c.level === "block");
            return (
              <article key={m.id} className="card model-card">
                <div className="row between">
                  <span className="badge mono">
                    {m.family.replaceAll("_", " ")}
                  </span>
                  <span className="small muted">In your browser</span>
                </div>
                <h2>{m.title}</h2>
                <p>{m.summary}</p>
                <span className="small">
                  <strong>{m.label}</strong>
                </span>
                {compatibility && (
                  <span
                    className={`status ${blocked ? "missing" : checks.some((c) => c.level === "warn") ? "limited" : "available"}`}
                  >
                    {blocked
                      ? "Incompatible"
                      : checks.some((c) => c.level === "warn")
                        ? "Compatible with notes"
                        : "Compatible"}
                  </span>
                )}
                <details>
                  <summary>Assumptions, inputs &amp; references</summary>
                  <ul>
                    {m.assumptions.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                  <p className="small">
                    Inputs: {text(m.inputs.min_series)}–
                    {text(m.inputs.max_series)} series. Required roles:{" "}
                    {text(m.inputs.required_roles, "any")}.
                  </p>
                  <p className="small">
                    {m.id.includes("var") || m.id === "ident.recursive"
                      ? "Pointwise bootstrap or asymptotic response intervals, conditional on the stated identification."
                      : ["lp.ols", "cmp.common_shock"].includes(m.id)
                        ? "Pointwise HC1 or HAC response bands; generated-shock uncertainty requires the on-demand joint bootstrap."
                        : m.id === "ident.external_series"
                          ? "Orthogonalised residuals from a first-stage VAR. Instability warns for shock extraction; unstable VAR responses remain blocked."
                          : m.id.startsWith("sing.")
                            ? "HAC or HC1 coefficient intervals describe sampling uncertainty; they do not establish causality."
                            : "Descriptive/test/filter output; uncertainty is shown where the method defines it."}
                  </p>
                  <ul>
                    {m.references.map((r) => (
                      <li key={r.url}>
                        <a href={r.url} target="_blank" rel="noreferrer">
                          {r.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                </details>
                {checks.length > 0 && (
                  <details open={blocked}>
                    <summary>Compatibility reasons ({checks.length})</summary>
                    {checks.map((c, i) => (
                      <p className="small" key={i}>
                        {c.country ? `${c.country}: ` : ""}
                        {c.message}
                      </p>
                    ))}
                  </details>
                )}
                <button
                  className={m.id === config.model.id ? "primary" : ""}
                  disabled={blocked || busy}
                  onClick={() => selectModel(m)}
                >
                  {m.id === config.model.id
                    ? "Current method"
                    : "Use this method"}
                </button>
              </article>
            );
          })}
      </div>
      <section className="card stack" aria-label="Planned methods">
        <h2>Planned · outside this release</h2>
        <p>
          <strong>v2 · planned:</strong> ARIMA / VAR forecasting and forecast
          evaluation, Bayesian VAR (Minnesota prior), panel fixed effects and
          panel LP, VECM / cointegration, structural-break tools.
        </p>
        <p>
          <strong>v3 · planned:</strong> sign restrictions, proxy SVAR / LP-IV,
          state-dependent LP, time-varying parameter VAR.
        </p>
      </section>
      <div className="info-box">
        The {manifest.models.length} validated plug-ins are enabled. Reference
        validation is method-specific; finite-sample coverage limits remain
        visible.
      </div>
    </section>
  );
}
export function MethodsValidation({ models }: { models: unknown }) {
  return (
    <div>
      {records(models).map((m) => (
        <p key={text(m.model_id)}>{text(m.model_id)}</p>
      ))}
    </div>
  );
}
