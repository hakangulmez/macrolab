import { Builder, type BuilderProps } from "./Builder";
import { Field, Checks, Status } from "./Common";
import { builderGuidance } from "../builderGuidance";
import {
  addFlowX,
  blankAnalysis,
  changeFlowModel,
  chooseShock,
  chooseY,
  flowY,
  removeFlowX,
  shockModels,
} from "../builderFlow";
import { record, title, transforms } from "../format";
import { coverage } from "../uiData";
import type { BuildMode } from "../simpleAnalysis";
import "./variable-first.css";

export function VariableFirstBuilder(
  props: BuilderProps & { mode: BuildMode },
) {
  const {
    manifest,
    config,
    setConfig,
    bundles,
    busy,
    run,
    check,
    checks,
    fix,
    openSource,
    mode,
    runtimeStatus,
    entryBlocked,
    recentResults,
  } = props;
  const y = flowY(config);
  const xs = config.series.filter((s) => s.concept_id !== y?.concept_id);
  const model = manifest.models.find((m) => m.id === config.model.id)!;
  const indicators = manifest.indicators.filter(
    (i) => record(i.publication).included !== false,
  );
  const selected = new Set(config.series.map((s) => s.concept_id));
  const template = Boolean(config.model.params.template_id);
  const guidance = builderGuidance(config, model);
  const blocked =
    Boolean(entryBlocked) ||
    guidance.length > 0 ||
    !y ||
    !config.countries.length;
  // Presentation labels only: roles and stored configuration remain unchanged.
  const regression =
    model.id.startsWith("sing.") ||
    ["test.granger", "panel.fe"].includes(model.id) ||
    (model.id === "test.break" &&
      config.model.params.host !== "ident.external_series");
  const forecast = ["uni.arima", "fc.var", "fc.eval"].includes(model.id);
  const projections = ["lp.ols", "panel.lp", "cmp.common_shock"].includes(
    model.id,
  );
  const system =
    [
      "var.ols",
      "ident.recursive",
      "ident.external_series",
      "out.hd",
      "bvar.minn",
      "test.coint",
      "vecm",
    ].includes(model.id) ||
    (model.id === "test.break" &&
      config.model.params.host === "ident.external_series");
  const primaryLabel = regression
    ? "Outcome variable"
    : forecast
      ? "Forecast target"
      : projections
        ? "Response variable"
        : "Variable of interest";
  const secondaryLabel = regression
    ? "Explanatory variables"
    : projections
      ? "Shock & controls"
      : model.id === "uni.arima"
        ? "External predictors"
        : system || forecast
          ? "Other variables & controls"
          : "Additional variables";
  const primaryHint = regression
    ? "What do you want to explain?"
    : forecast
      ? "What do you want to forecast?"
      : projections
        ? "Which response do you want to study?"
        : "What do you want to study?";
  const secondaryHint = regression
    ? "What might explain it?"
    : projections
      ? "Which shock and controls?"
      : "What else should be included?";
  const cells = coverage(manifest);
  const name = (id: string) =>
    id === "identified_impulse"
      ? "Identified EA policy shock"
      : title(id, manifest.indicators);
  const update = (fn: (c: typeof config) => void) => {
    const c = structuredClone(config);
    fn(c);
    setConfig(c);
  };
  const transformControl = (id: string, transform: string) => (
    <select
      aria-label={`Transform for ${name(id)}`}
      value={transform}
      disabled={id === "identified_impulse" || template}
      onChange={(e) =>
        update((c) => {
          const s = c.series.find((s) => s.concept_id === id)!;
          s.transform = e.target.value;
          s.transform_params =
            s.transform === "index_to_base"
              ? { base_period: c.sample.start }
              : {};
        })
      }
    >
      {Object.entries(transforms)
        .filter(([key]) => key !== "qoq_saar" || config.frequency === "Q")
        .map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
    </select>
  );
  return (
    <section className="variable-builder" data-testid="screen-builder">
      <div className="flow-heading">
        <div>
          <span className="overline">Your research question</span>
          <h1>Build an analysis</h1>
          <p>Choose your variables, a model and where to study them.</p>
        </div>
        <button
          className="flow-reset"
          onClick={() => setConfig(blankAnalysis(manifest))}
        >
          New custom analysis
        </button>
      </div>
      {template && (
        <p className="info-box small">
          This template keeps its defined variables and method. All stored
          settings are preserved. Choose “New custom analysis” to build your
          own.
        </p>
      )}
      <div className="variable-flow">
        <section className="flow-card" aria-labelledby="flow-y-heading">
          <h2 id="flow-y-heading">
            <span className="flow-number">1</span> {primaryLabel}{" "}
            <span className="flow-caption">{primaryHint}</span>
          </h2>
          <Field label="Select a variable">
            <select
              data-testid="flow-y"
              value={y?.concept_id ?? ""}
              disabled={template}
              onChange={(e) => {
                const i = indicators.find(
                  (i) => i.concept_id === e.target.value,
                );
                if (i) setConfig(chooseY(config, i));
              }}
            >
              <option value="" disabled>
                Choose a variable…
              </option>
              {indicators.map((i) => (
                <option
                  key={i.concept_id}
                  value={i.concept_id}
                  disabled={config.series.some(
                    (s) =>
                      s.concept_id === i.concept_id &&
                      s.role === "shock" &&
                      s !== y,
                  )}
                >
                  {i.title}
                </option>
              ))}
            </select>
          </Field>
          {y ? (
            <div className="flow-transform">
              <span className="small muted">Use as</span>
              {transformControl(y.concept_id, y.transform)}
            </div>
          ) : (
            <p className="small muted">
              Choose the main series you want to study. Its role follows the
              selected model.
            </p>
          )}
        </section>
        <section className="flow-card" aria-labelledby="flow-x-heading">
          <h2 id="flow-x-heading">
            <span className="flow-number">2</span> {secondaryLabel}{" "}
            <span className="flow-caption">{secondaryHint}</span>
          </h2>
          <Field
            label={
              regression
                ? "Add an explanatory variable"
                : "Add another variable"
            }
          >
            <select
              data-testid="flow-add-x"
              disabled={!y || template}
              value=""
              onChange={(e) => {
                const i = indicators.find(
                  (i) => i.concept_id === e.target.value,
                );
                if (i) setConfig(addFlowX(config, i));
              }}
            >
              <option value="">Choose a variable…</option>
              {indicators
                .filter((i) => !selected.has(i.concept_id))
                .map((i) => (
                  <option key={i.concept_id} value={i.concept_id}>
                    {i.title}
                  </option>
                ))}
            </select>
          </Field>
          <div className="flow-xs">
            {xs.map((s) => (
              <div className="flow-x" key={s.concept_id}>
                <span>
                  {name(s.concept_id)}
                  {["shock", "exogenous"].includes(s.role) && (
                    <small className="muted">
                      {" "}
                      · {s.role === "shock" ? "shock" : "external control"}
                    </small>
                  )}
                </span>
                {transformControl(s.concept_id, s.transform)}
                <button
                  disabled={template || s.concept_id === "identified_impulse"}
                  aria-label={`Remove variable ${name(s.concept_id)}`}
                  onClick={() => setConfig(removeFlowX(config, s.concept_id))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          {!xs.length && (
            <p className="small muted">
              Optional for plots, filters and single-series forecasts.
            </p>
          )}
        </section>
        <section className="flow-card" aria-labelledby="flow-model-heading">
          <h2 id="flow-model-heading">
            <span className="flow-number">3</span> Model{" "}
            <span className="flow-caption">How should we analyse it?</span>
          </h2>
          <Field label="Econometric model">
            <select
              data-testid="flow-model"
              disabled={template}
              value={config.model.id}
              onChange={(e) =>
                setConfig(changeFlowModel(config, e.target.value))
              }
            >
              {manifest.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.title}
                </option>
              ))}
            </select>
          </Field>
          <p className="small muted">{model.summary}</p>
          {props.browseMethods && (
            <button className="flow-method-help" onClick={props.browseMethods}>
              Model guide & assumptions
            </button>
          )}
          {config.identification?.id === "recursive" && (
            <p className="small muted">
              Recursive order:{" "}
              {config.identification.params.order.map(name).join(" → ")}. Review
              the ordering in Sample & model settings.
            </p>
          )}
          {shockModels.includes(model.id) &&
            model.id !== "cmp.common_shock" &&
            !template && (
              <Field label="Shock variable">
                <select
                  value={
                    config.series.find((s) => s.role === "shock")?.concept_id ??
                    ""
                  }
                  onChange={(e) =>
                    setConfig(chooseShock(config, e.target.value))
                  }
                >
                  <option value="">Choose a shock variable…</option>
                  {xs
                    .filter((s) => s.concept_id !== "identified_impulse")
                    .map((s) => (
                      <option key={s.concept_id} value={s.concept_id}>
                        {name(s.concept_id)}
                      </option>
                    ))}
                </select>
              </Field>
            )}
          {y &&
            guidance.filter((s) => !s.startsWith("Choose at least one country"))
              .length > 0 && (
              <p className="small flow-hint">
                {guidance
                  .filter((s) => !s.startsWith("Choose at least one country"))
                  .join(" ")}
              </p>
            )}
        </section>
        <section className="flow-card" aria-labelledby="flow-countries-heading">
          <h2 id="flow-countries-heading">
            <span className="flow-number">4</span> Country / countries{" "}
            <span className="flow-caption">Where?</span>
          </h2>
          <Field label="Add country">
            <select
              data-testid="flow-country"
              value=""
              onChange={(e) => {
                if (e.target.value)
                  update((c) => {
                    c.countries.push(e.target.value);
                  });
              }}
            >
              <option value="">Choose a country…</option>
              {manifest.countries
                .filter(
                  (c) =>
                    !config.countries.includes(c.iso3) &&
                    (config.model.params.template_id !== "same_ecb_shock" ||
                      (c.monetary_union === "EA" && c.iso3 !== "EA")),
                )
                .map((c) => {
                  const available = config.series
                    .filter((s) => s.concept_id !== "identified_impulse")
                    .filter((s) =>
                      cells.some(
                        (cell) =>
                          cell.country === c.iso3 &&
                          cell.concept_id === s.concept_id &&
                          cell.status !== "missing",
                      ),
                    );
                  return (
                    <option value={c.iso3} key={c.iso3}>
                      {c.name}
                      {config.series.length
                        ? ` · ${available.length}/${config.series.filter((s) => s.concept_id !== "identified_impulse").length} series`
                        : ""}
                    </option>
                  );
                })}
            </select>
          </Field>
          <div className="flow-countries">
            {config.countries.map((iso) => (
              <div className="flow-country-chip" key={iso}>
                <span>
                  {manifest.countries.find((c) => c.iso3 === iso)?.name ?? iso}
                </span>
                <button
                  aria-label={`Remove country ${iso}`}
                  onClick={() =>
                    update((c) => {
                      c.countries = c.countries.filter((x) => x !== iso);
                    })
                  }
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <p className="small muted">
            {model.id.startsWith("panel.")
              ? "The selected panel model pools the chosen countries."
              : model.id === "cmp.common_shock"
                ? "Countries are compared using the same identified shock."
                : "The same model runs for each country. Adding countries does not select a panel model."}
          </p>
          {config.countries.length > 0 && config.series.length > 0 && (
            <details className="flow-coverage">
              <summary>
                Data coverage · {config.countries.length}{" "}
                {config.countries.length === 1 ? "country" : "countries"}
              </summary>
              {config.countries.map((iso) => (
                <div key={iso}>
                  <strong>{iso}</strong>
                  {config.series
                    .filter((s) => s.concept_id !== "identified_impulse")
                    .map((s) => {
                      const cell = cells.find(
                          (c) =>
                            c.country === iso && c.concept_id === s.concept_id,
                        ),
                        card = bundles[iso]?.cards.find(
                          (c) => c.concept_id === s.concept_id,
                        );
                      return (
                        <div className="flow-coverage-row" key={s.concept_id}>
                          <button
                            onClick={() => openSource?.(iso, s.concept_id)}
                          >
                            {name(s.concept_id)}
                          </button>
                          <Status
                            status={card?.status ?? cell?.status ?? "loading"}
                          />
                          <span>
                            {card?.first_date ?? cell?.first_date ?? "—"} →{" "}
                            {card?.last_date ?? cell?.last_date ?? "—"}
                          </span>
                        </div>
                      );
                    })}
                </div>
              ))}
            </details>
          )}
        </section>
      </div>
      <details className="flow-settings" key={mode} open={mode === "advanced"}>
        <summary>
          <span>Sample &amp; model settings</span>
          <span className="small muted">
            {config.frequency === "Q"
              ? "Quarterly"
              : config.frequency === "M"
                ? "Monthly"
                : "Annual"}{" "}
            · {config.sample.start}–{config.sample.end}
          </span>
        </summary>
        <p className="small muted">
          These are the settings used by this analysis. Simple and Advanced
          share the same configuration.
        </p>
        <Builder {...props} settingsOnly />
      </details>
      <div className="flow-run">
        <div>
          <strong>
            {y
              ? `${name(y.concept_id)}${xs.length ? ` ~ ${xs.map((s) => name(s.concept_id)).join(" + ")}` : ""}`
              : "Choose your main variable to begin"}
          </strong>
          <p className="small muted">
            {model.title} · {config.countries.length}{" "}
            {config.countries.length === 1 ? "country" : "countries"} ·{" "}
            {busy
              ? "Working locally…"
              : runtimeStatus === "preparing"
                ? "Preparing the engine; you can keep editing."
                : "Calculated locally in your browser."}
          </p>
        </div>
        <button
          data-testid="run-analysis"
          className="primary"
          disabled={busy || blocked}
          onClick={run}
        >
          Run analysis →
        </button>
      </div>
      <div className="flow-checks">
        <button
          onClick={check}
          disabled={busy || !y || !config.countries.length}
        >
          Check compatibility
        </button>
        {checks.length > 0 && (
          <Checks
            checks={checks}
            onFix={fix}
            onSourceCard={openSource}
            countries={manifest.countries}
            indicators={manifest.indicators}
          />
        )}
      </div>
      {recentResults && (
        <details className="flow-recent">
          <summary>Recent analyses</summary>
          {recentResults}
        </details>
      )}
    </section>
  );
}
