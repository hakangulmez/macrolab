import { diagnosticModel } from "../diagnosticModels";
import { forecastModel } from "../forecast";
import { useState } from "react";
import type { AnalysisConfig, Manifest, Model } from "../types";
import { records, text } from "../format";
const validationCards: Record<string, string> = {
  "panel.fe": "panel_fe",
  "panel.lp": "panel_lp",
  "bvar.minn": "bvar_minn",
  "uni.arima": "forecasting",
  "fc.var": "forecasting",
  "fc.eval": "forecasting",
  "test.coint": "cointegration",
  vecm: "cointegration",
  "test.break": "break-tests",
};
export { Home } from "./HomeV3";
export function Library({
  manifest,
  compatibility,
  check,
  busy,
  selectModel,
  config,
  embedded = false,
}: {
  manifest: Manifest;
  compatibility: Model[] | null;
  check: () => void;
  busy: boolean;
  selectModel: (m: Model) => void;
  config: AnalysisConfig;
  embedded?: boolean;
}) {
  const Heading = embedded ? "h3" : "h1";
  const CardHeading = embedded ? "h4" : "h2";
  const [family, setFamily] = useState("All");
  const models = compatibility ?? manifest.models;
  const families = ["All", ...new Set(models.map((m) => m.family))];
  return (
    <section data-testid="screen-library" className="stack">
      <div className="page-heading">
        <span className="overline">Model library · validated methods</span>
        <Heading>A method for the question you’re asking.</Heading>
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
                <CardHeading>{m.title}</CardHeading>
                <p>{m.summary}</p>
                {validationCards[m.id] && (
                  <a
                    href={`${import.meta.env.BASE_URL}validation/${validationCards[m.id]}.html`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Validation card
                  </a>
                )}
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
                    {forecastModel(m.id)
                      ? "Predictive uncertainty in original units, explicit future controls and final-vintage evaluation."
                      : m.id.includes("var") || m.id === "ident.recursive"
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
                  disabled={
                    (blocked &&
                      !m.id.startsWith("panel.") &&
                      m.id !== "bvar.minn" &&
                      !forecastModel(m.id) &&
                      !diagnosticModel(m.id)) ||
                    busy
                  }
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
        {!manifest.templates.some(
          (t) => t.id === "ea_inflation_horse_race",
        ) && (
          <p>
            <strong>v2 · planned:</strong> panel and forecasting horse-race
            templates.
          </p>
        )}
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
