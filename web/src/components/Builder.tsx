import { builderGuidance, suggestedRoles } from "../builderGuidance";
import { parameterDisplayLabel } from "../chartDisplay";
import { FirstStageInput } from "./FirstStageInput";
import { ForecastControls } from "./ForecastControls";
import { DiagnosticControls } from "./DiagnosticControls";
import { diagnosticModel } from "../diagnosticModels";
import { forecastModel } from "../forecast";
import { BvarControls } from "./BvarControls";
import { countryIndicators } from "../displayLabels";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type {
  AnalysisConfig,
  Card,
  Check,
  CountryBundle,
  JsonRecord,
  Manifest,
  Model,
  SeriesSpec,
} from "../types";
import {
  formulas,
  indicatorSummary,
  number,
  record,
  text,
  title,
  transforms,
} from "../format";
import { Checks, Field, Status } from "./Common";
import "./builder.css";
import { PanelControls } from "./PanelControls";
import { TemplateControls } from "./TemplateControls";
interface Props {
  browseMethods?: () => void;
  methodsOpen?: boolean;
  methodBrowser?: ReactNode;
  recentResults?: ReactNode;
  manifest: Manifest;
  config: AnalysisConfig;
  setConfig: (c: AnalysisConfig) => void;
  bundles: Record<string, CountryBundle>;
  models: Model[] | null;
  checks: Check[];
  busy: boolean;
  runtimeStatus?: string;
  run: () => void;
  check: () => void;
  fix: (v: JsonRecord) => void;
  openSource?: (country: string, conceptId: string) => void;
}
export function Builder({
  browseMethods,
  methodsOpen,
  methodBrowser,
  recentResults,
  manifest,
  config,
  setConfig,
  bundles,
  models,
  checks,
  busy,
  runtimeStatus = "idle",
  run,
  check,
  fix,
  openSource,
}: Props) {
  const browserSlot = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (methodsOpen) {
      browserSlot.current?.scrollIntoView({ block: "start" });
      browserSlot.current
        ?.querySelector<HTMLElement>("#browse-methods")
        ?.focus();
    }
  }, [methodsOpen]);
  const [countrySearch, setCountrySearch] = useState("");
  const [indicatorSearch, setIndicatorSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [step, setStep] = useState("Countries");
  const update = (fn: (next: AnalysisConfig) => void) => {
    const next = structuredClone(config);
    fn(next);
    setConfig(next);
  };
  const model = manifest.models.find((m) => m.id === config.model.id)!;
  const vars = config.series.filter((s) =>
    ["endogenous", "response", "shock"].includes(s.role),
  );
  const guidance = builderGuidance(config, model);
  const suggestion = suggestedRoles(config);
  const blocked = guidance.length > 0;
  const isTemplate = Boolean(config.model.params.template_id);
  const isBvar = model.id === "bvar.minn";
  const isVar = ["var.ols", "ident.recursive", "bvar.minn"].includes(model.id);
  const selected = new Set(config.series.map((s) => s.concept_id));
  const categories = [
    "All",
    ...new Set(manifest.indicators.map((i) => i.category ?? "Indicators")),
  ];
  const candidates = manifest.indicators.filter(
    (i) =>
      record(i.publication).included !== false &&
      !selected.has(i.concept_id) &&
      (category === "All" || i.category === category) &&
      `${i.title} ${i.concept_id}`
        .toLowerCase()
        .includes(indicatorSearch.toLowerCase()),
  );
  function setSeries(index: number, changes: Partial<SeriesSpec>) {
    update((c) => {
      c.series[index] = { ...c.series[index], ...changes };
      if (changes.transform)
        c.series[index].transform_params =
          changes.transform === "index_to_base"
            ? { base_period: c.sample.start }
            : {};
      if (c.identification)
        c.identification.params.order = c.series
          .filter((s) => ["shock", "response", "endogenous"].includes(s.role))
          .map((s) => s.concept_id);
    });
  }
  function selectModel(id: string) {
    update((c) => {
      c.model = { id, params: {} };
      if (!["var.ols", "ident.recursive", "bvar.minn"].includes(id)) {
        c.identification = null;
        delete c.outputs.irf;
      } else if (["ident.recursive", "bvar.minn"].includes(id)) {
        c.identification = {
          id: "recursive",
          params: { order: vars.map((s) => s.concept_id) },
        };
        c.outputs.irf ??= {
          horizon: 12,
          bands: 0.68,
          shock_size: 1,
          shock_mode: "one_sd",
          method: "bootstrap",
          draws: 200,
        };
      }
    });
  }
  const card = (iso: string, id: string): Card | undefined =>
    bundles[iso]?.cards.find((c) => c.concept_id === id);
  return (
    <section data-testid="screen-builder" className="compact-builder">
      <div className="page-heading">
        <span className="overline">Your workspace</span>
        <h1>Build an analysis</h1>
        <p>
          Choose the sample and assumptions. We’ll check what the data can
          support.
        </p>
      </div>
      <nav className="stepper" aria-label="Analysis steps">
        {["Countries", "Indicators", "Model", "Results"].map((name, i) => (
          <button
            key={name}
            className={step === name ? "active" : ""}
            onClick={() => {
              setStep(name);
              if (name === "Results") {
                document
                  .querySelector("[data-testid=run-analysis]")
                  ?.scrollIntoView({ block: "center" });
              } else
                document
                  .getElementById(`step-${name}`)
                  ?.scrollIntoView({ block: "start" });
            }}
          >
            {i + 1} · {name}
          </button>
        ))}
      </nav>
      <div ref={browserSlot}>{methodBrowser}</div>
      <div className="builder-grid">
        <div className="stack">
          <section id="step-Countries" className="card stack">
            <h2>1 · Countries</h2>
            <div className="country-chips">
              {config.countries.map((iso) => (
                <button
                  key={iso}
                  disabled={config.countries.length === 1}
                  aria-label={`Remove ${iso} · ${manifest.countries.find((c) => c.iso3 === iso)?.name}`}
                  onClick={() =>
                    update((c) => {
                      c.countries = c.countries.filter((x) => x !== iso);
                    })
                  }
                >
                  {iso} · {manifest.countries.find((c) => c.iso3 === iso)?.name}{" "}
                  <span aria-hidden="true">×</span>
                </button>
              ))}
            </div>
            <div className="two-fields country-picker">
              <Field label="Find a country">
                <input
                  placeholder="Search countries"
                  type="search"
                  value={countrySearch}
                  onChange={(e) => setCountrySearch(e.target.value)}
                />
              </Field>
              <Field label="Add country">
                <select
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
                          (c.monetary_union === "EA" && c.iso3 !== "EA")) &&
                        `${c.name} ${c.iso3}`
                          .toLowerCase()
                          .includes(countrySearch.toLowerCase()),
                    )
                    .map((c) => (
                      <option key={c.iso3} value={c.iso3}>
                        {c.name}
                        {c.monetary_union === "EA" ? " · ECB rate shared" : ""}
                      </option>
                    ))}
                </select>
              </Field>
            </div>
            <p className="small muted">
              Each country retains its own actual sample. Euro-area policy
              shocks use the shared ECB rate and respect adoption dates.
            </p>
          </section>
          <section id="step-Indicators" className="card stack">
            <div className="row between">
              <h2>2 · Indicators</h2>
              <span className="small muted">
                {config.series.length} selected
              </span>
            </div>
            <div className="compact-selection-list">
              {config.series.map((s, i) => (
                <article
                  className="compact-series"
                  key={s.concept_id}
                  aria-labelledby={`selected-${s.concept_id}`}
                >
                  <div className="compact-series-name">
                    <h3 id={`selected-${s.concept_id}`}>
                      {s.concept_id === "identified_impulse"
                        ? "Identified EA policy shock"
                        : title(
                            s.concept_id,
                            countryIndicators(
                              manifest.indicators,
                              config.countries[0],
                            ),
                          )}
                    </h3>
                    <span className="small muted">
                      {manifest.indicators.find(
                        (indicator) => indicator.concept_id === s.concept_id,
                      )?.frequency ?? config.frequency}
                    </span>
                  </div>
                  <Field label="Role">
                    <select
                      aria-label={`Role for ${title(s.concept_id, countryIndicators(manifest.indicators, config.countries[0]))}`}
                      value={s.role}
                      disabled={s.concept_id === "identified_impulse"}
                      onChange={(e) => setSeries(i, { role: e.target.value })}
                    >
                      {[
                        "shock",
                        "response",
                        "endogenous",
                        "exogenous",
                        "dependent",
                        "regressor",
                      ].map((r) => (
                        <option key={r}>{r}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Transform">
                    <select
                      aria-label={`Transform for ${title(s.concept_id, countryIndicators(manifest.indicators, config.countries[0]))}`}
                      value={s.transform}
                      disabled={s.concept_id === "identified_impulse"}
                      onChange={(e) =>
                        setSeries(i, { transform: e.target.value })
                      }
                    >
                      {Object.entries(transforms)
                        .filter(
                          ([key]) =>
                            key !== "qoq_saar" || config.frequency === "Q",
                        )
                        .map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                    </select>
                  </Field>
                  <div className="compact-series-coverage">
                    <span className="compact-field-label">Coverage</span>
                    {(s.concept_id === "identified_impulse"
                      ? ["EA"]
                      : config.countries
                    ).map((iso) => {
                      if (s.concept_id === "identified_impulse")
                        return (
                          <span key={iso} className="small">
                            Computed in EA stage 1; dates verified at
                            estimation.
                          </span>
                        );
                      const info = card(iso, s.concept_id);
                      const content = (
                        <>
                          <span>
                            {iso} <Status status={info?.status ?? "loading"} />
                          </span>
                          <span className="compact-coverage-dates">
                            {info?.first_date ?? "—"} → {info?.last_date ?? "—"}
                          </span>
                        </>
                      );
                      return openSource ? (
                        <button
                          key={iso}
                          className="compact-coverage-link"
                          onClick={() => openSource(iso, s.concept_id)}
                        >
                          {content}
                        </button>
                      ) : (
                        <div key={iso}>{content}</div>
                      );
                    })}
                  </div>
                  <button
                    className="compact-series-remove"
                    disabled={s.concept_id === "identified_impulse"}
                    aria-label={`Remove ${title(s.concept_id, countryIndicators(manifest.indicators, config.countries[0]))}`}
                    onClick={() =>
                      update((c) => {
                        c.series = c.series.filter(
                          (x) => x.concept_id !== s.concept_id,
                        );
                        delete c.aggregation[s.concept_id];
                        if (c.identification)
                          c.identification.params.order =
                            c.identification.params.order.filter(
                              (x) => x !== s.concept_id,
                            );
                      })
                    }
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                  <details className="compact-series-advanced">
                    <summary>Advanced</summary>
                    <p className="small muted">{formulas[s.transform]}</p>
                    <div className="two-fields">
                      {s.transform === "index_to_base" && (
                        <Field label="Index base">
                          <input
                            aria-label={`Index base for ${title(s.concept_id, countryIndicators(manifest.indicators, config.countries[0]))}`}
                            value={text(s.transform_params?.base_period, "")}
                            onChange={(e) =>
                              setSeries(i, {
                                transform_params: {
                                  ...s.transform_params,
                                  base_period: e.target.value,
                                },
                              })
                            }
                          />
                        </Field>
                      )}
                      <Field label="Aggregation">
                        <select
                          aria-label={`Aggregation for ${title(s.concept_id, countryIndicators(manifest.indicators, config.countries[0]))}`}
                          value={config.aggregation[s.concept_id] ?? "mean"}
                          onChange={(e) =>
                            update((c) => {
                              c.aggregation[s.concept_id] = e.target.value;
                            })
                          }
                        >
                          <option value="mean">Complete-period mean</option>
                          <option value="last">
                            Last (verified stocks only)
                          </option>
                          <option value="sum">Sum (verified flows only)</option>
                        </select>
                      </Field>
                    </div>
                    {config.countries.map(
                      (iso) =>
                        card(iso, s.concept_id)?.policy_label && (
                          <p className="small muted" key={iso}>
                            {iso}: {card(iso, s.concept_id)?.policy_label}
                          </p>
                        ),
                    )}
                  </details>
                </article>
              ))}
            </div>
            <hr className="divider" />
            <h3>Add an indicator</h3>
            <div className="category-tabs">
              {categories.map((c) => (
                <button
                  key={c}
                  aria-pressed={category === c}
                  onClick={() => setCategory(c)}
                >
                  {c}
                </button>
              ))}
            </div>
            <input
              aria-label={`Search ${indicatorSummary(manifest)}`}
              placeholder={`Search ${indicatorSummary(manifest)}`}
              type="search"
              value={indicatorSearch}
              onChange={(e) => setIndicatorSearch(e.target.value)}
            />
            <div className="scroll-list stack">
              {candidates.map((i) => (
                <button
                  key={i.concept_id}
                  className="row between"
                  onClick={() =>
                    update((c) => {
                      const role =
                        i.scope === "global"
                          ? "exogenous"
                          : isVar
                            ? "endogenous"
                            : c.series.some((s) => s.role === "dependent")
                              ? "regressor"
                              : "dependent";
                      c.series.push({
                        concept_id: i.concept_id,
                        role,
                        transform: i.default_transform ?? "level",
                        transform_params: {},
                      });
                      c.aggregation[i.concept_id] = "mean";
                      if (c.identification && role === "endogenous")
                        c.identification.params.order.push(i.concept_id);
                    })
                  }
                >
                  <span>{i.title}</span>
                  <span className="small muted">
                    {i.scope === "global" ? "Global factor" : text(i.frequency)}{" "}
                    · Add +
                  </span>
                </button>
              ))}
            </div>
          </section>
          {model.id === "cmp.common_shock" && !isTemplate && (
            <FirstStageInput
              config={config}
              manifest={manifest}
              update={update}
            />
          )}
        </div>
        <aside className="stack sidebar">
          <section id="step-Model" className="card stack">
            <h2>3 · Model &amp; sample</h2>
            <div className="method-picker-row">
              <Field label="Method">
                <select
                  value={config.model.id}
                  disabled={isTemplate}
                  onChange={(e) => selectModel(e.target.value)}
                >
                  {manifest.models.map((m) => (
                    <option
                      key={m.id}
                      value={m.id}
                      disabled={
                        !m.id.startsWith("panel.") &&
                        !forecastModel(m.id) &&
                        m.id !== "bvar.minn" &&
                        !diagnosticModel(m.id) &&
                        models?.find((x) => x.id === m.id)?.available === false
                      }
                    >
                      {m.title}
                    </option>
                  ))}
                </select>
              </Field>
              {browseMethods && (
                <button
                  onClick={browseMethods}
                  aria-expanded={Boolean(methodsOpen)}
                  aria-controls="browse-methods"
                >
                  Browse methods
                </button>
              )}
            </div>
            <p className="small muted">{model.summary}</p>
            {blocked && (
              <section
                className="warning-box stack"
                data-testid="builder-guidance"
                aria-label="Before you run"
              >
                <h3>Before you run</h3>
                <ul>
                  {guidance.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
                {suggestion && (
                  <>
                    <p className="small">
                      Suggested roles (same indicators, order and transforms):{" "}
                      {suggestion.series
                        .map(
                          (s) =>
                            `${title(s.concept_id, countryIndicators(manifest.indicators, config.countries[0]))} → ${s.role}`,
                        )
                        .join("; ")}
                    </p>
                    <button onClick={() => setConfig(suggestion)}>
                      Apply suggested roles
                    </button>
                  </>
                )}
              </section>
            )}
            <div className="two-fields">
              <Field label="Frequency">
                <select
                  value={config.frequency}
                  disabled={isTemplate}
                  onChange={(e) =>
                    update((c) => {
                      c.frequency = e.target.value;
                      c.sample = {
                        start:
                          e.target.value === "Q"
                            ? "1999-Q1"
                            : e.target.value === "M"
                              ? "1999-01"
                              : "1999",
                        end: "latest",
                      };
                    })
                  }
                >
                  <option value="Q">Quarterly</option>
                  <option value="M">Monthly</option>
                  <option value="A">Annual</option>
                </select>
              </Field>
              <Field label="Random seed">
                <input
                  type="number"
                  min="0"
                  value={config.seed}
                  onChange={(e) =>
                    update((c) => {
                      c.seed = Number(e.target.value);
                    })
                  }
                />
              </Field>
            </div>
            <div className="two-fields">
              <Field label="Sample start">
                <input
                  value={config.sample.start}
                  onChange={(e) =>
                    update((c) => {
                      c.sample.start = e.target.value;
                    })
                  }
                />
              </Field>
              <Field label="Sample end">
                <input
                  value={config.sample.end}
                  placeholder="latest"
                  onChange={(e) =>
                    update((c) => {
                      c.sample.end = e.target.value;
                    })
                  }
                />
              </Field>
            </div>
            <Field label="COVID treatment">
              <select
                value={config.special_periods.covid}
                onChange={(e) =>
                  update((c) => {
                    c.special_periods.covid = e.target.value;
                  })
                }
              >
                <option value="dummy">Impulse dummies</option>
                <option value="include">Include</option>
                <option value="exclude">Exclude</option>
              </select>
            </Field>
            <p className="small muted">
              Treatment window:{" "}
              {config.special_periods.covid_window
                ? `${config.special_periods.covid_window.start}–${config.special_periods.covid_window.end}`
                : "2020 Q1–2021 Q2"}
              .
            </p>
            <TemplateControls config={config} update={update} />
            <PanelControls
              config={config}
              manifest={manifest}
              update={update}
            />
            <BvarControls config={config} manifest={manifest} update={update} />
            <DiagnosticControls
              config={config}
              manifest={manifest}
              update={update}
            />
            <ForecastControls
              config={config}
              manifest={manifest}
              update={update}
            />
            <details>
              <summary>Model parameters</summary>
              <div className="stack">
                {Object.entries(model.params.properties ?? {})
                  .filter(
                    ([key, rule]) =>
                      !forecastModel(model.id) &&
                      !diagnosticModel(model.id) &&
                      ["integer", "number", "string"].includes(
                        String(rule.type),
                      ) &&
                      ![
                        "template_id",
                        "policy_measure",
                        "country_window",
                        "displayed_band",
                        "response_mode",
                        "covariance",
                        "effects",
                        "shock_type",
                        "first_stage_source",
                      ].includes(key) &&
                      (!isTemplate || ["lags", "horizon"].includes(key)) &&
                      (!isBvar || !["draws", "lambda_selection"].includes(key)),
                  )
                  .map(([key, rule]) => (
                    <Field key={key} label={parameterDisplayLabel(key)}>
                      {Array.isArray(rule.enum) ? (
                        <select
                          value={text(
                            config.model.params[key] ?? rule.default,
                            "",
                          )}
                          onChange={(e) =>
                            update((c) => {
                              c.model.params[key] = e.target.value;
                            })
                          }
                        >
                          {rule.enum.map((v) => (
                            <option key={text(v)} value={text(v)}>
                              {parameterDisplayLabel(text(v))}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="number"
                          step={rule.type === "integer" ? 1 : "any"}
                          min={
                            typeof rule.minimum === "number"
                              ? rule.minimum
                              : undefined
                          }
                          max={
                            typeof rule.maximum === "number"
                              ? rule.maximum
                              : undefined
                          }
                          value={Number(
                            config.model.params[key] ??
                              rule.default ??
                              (key === "lambda" ? 1600 : 0),
                          )}
                          onChange={(e) =>
                            update((c) => {
                              c.model.params[key] = Number(e.target.value);
                              if (
                                key === "lags" &&
                                c.model.params.template_id === "same_ecb_shock"
                              )
                                (
                                  c.model.params.first_stage as AnalysisConfig
                                ).model.params.lags = Number(e.target.value);
                              if (key === "confidence")
                                c.outputs.confidence = Number(e.target.value);
                            })
                          }
                        />
                      )}
                    </Field>
                  ))}
              </div>
            </details>
            {[
              "var.ols",
              "ident.recursive",
              "bvar.minn",
              "out.hd",
              "ident.external_series",
            ].includes(model.id) && (
              <>
                <Field label="Identification">
                  <select
                    id="identification-control"
                    value={config.identification ? "recursive" : "none"}
                    onChange={(e) =>
                      update((c) => {
                        c.identification =
                          e.target.value === "recursive"
                            ? {
                                id: "recursive",
                                params: {
                                  order: vars.map((v) => v.concept_id),
                                },
                              }
                            : null;
                        if (c.identification)
                          c.outputs.irf ??= {
                            horizon: 12,
                            bands: 0.68,
                            shock_size: 1,
                            shock_mode: "one_sd",
                            method: "bootstrap",
                            draws: 200,
                          };
                      })
                    }
                  >
                    <option value="none" disabled={isBvar}>
                      Reduced form only
                    </option>
                    <option value="recursive">Recursive (Cholesky)</option>
                  </select>
                </Field>
                {config.identification && (
                  <>
                    <Field label="Shock size">
                      <select
                        value={
                          config.outputs.irf?.shock_mode === "one_sd"
                            ? "one_sd"
                            : String(config.outputs.irf?.shock_size)
                        }
                        onChange={(e) =>
                          update((c) => {
                            c.outputs.irf = {
                              ...c.outputs.irf!,
                              shock_mode:
                                e.target.value === "one_sd"
                                  ? "one_sd"
                                  : "fixed",
                              shock_size:
                                e.target.value === "one_sd"
                                  ? 1
                                  : Number(e.target.value),
                            };
                          })
                        }
                      >
                        <option value="one_sd">
                          One identified standard deviation
                        </option>
                        <option value="0.25">+25 bp</option>
                        <option value="1">+1 percentage point</option>
                        {config.outputs.irf?.shock_mode !== "one_sd" &&
                          ![0.25, 1].includes(
                            config.outputs.irf?.shock_size ?? 1,
                          ) && (
                            <option value={config.outputs.irf?.shock_size}>
                              Custom shock
                            </option>
                          )}
                      </select>
                    </Field>
                    <div className="two-fields">
                      <Field label="IRF horizon">
                        <input
                          type="number"
                          min="1"
                          max="80"
                          value={config.outputs.irf?.horizon ?? 12}
                          onChange={(e) =>
                            update((c) => {
                              c.outputs.irf!.horizon = Number(e.target.value);
                            })
                          }
                        />
                      </Field>
                      {!isBvar && (
                        <Field label="Bootstrap precision">
                          <select
                            value={config.outputs.irf?.draws ?? 200}
                            onChange={(e) =>
                              update((c) => {
                                c.outputs.irf!.draws = Number(e.target.value);
                              })
                            }
                          >
                            <option value={200}>Interactive · 200 draws</option>
                            <option value={1000}>Precise · 1,000 draws</option>
                            {config.outputs.irf?.draws !== undefined &&
                              ![200, 1000].includes(
                                config.outputs.irf.draws,
                              ) && (
                                <option value={config.outputs.irf.draws}>
                                  Current ·{" "}
                                  {config.outputs.irf.draws.toLocaleString()}{" "}
                                  draws
                                </option>
                              )}
                          </select>
                        </Field>
                      )}
                    </div>
                    <details>
                      <summary>Recursive ordering</summary>
                      <p className="small muted">
                        Earlier variables do not respond on impact to later
                        shocks.
                      </p>
                      {config.identification.params.order.map((v, i) => (
                        <div className="order-row" key={v}>
                          <span className="small">
                            {i + 1}.{" "}
                            {title(
                              v,
                              countryIndicators(
                                manifest.indicators,
                                config.countries[0],
                              ),
                            )}
                          </span>
                          <button
                            aria-label={`Move ${v} earlier`}
                            disabled={i === 0}
                            onClick={() =>
                              update((c) => {
                                const a = c.identification!.params.order;
                                [a[i - 1], a[i]] = [a[i], a[i - 1]];
                              })
                            }
                          >
                            ↑
                          </button>
                        </div>
                      ))}
                    </details>
                  </>
                )}
              </>
            )}
            <p className="small">
              <strong>{model.label}</strong>
            </p>
          </section>
          <button onClick={check} disabled={busy}>
            Check compatibility
          </button>
          <Checks
            checks={checks}
            onFix={fix}
            onSourceCard={openSource}
            countries={manifest.countries}
            indicators={manifest.indicators}
          />
          <p
            className="small muted"
            role="status"
            data-testid="runtime-readiness"
            data-runtime-status={runtimeStatus}
          >
            {busy
              ? "Working locally…"
              : runtimeStatus === "preparing"
                ? "Preparing the analysis engine… You can keep editing."
                : runtimeStatus === "ready"
                  ? "Ready to calculate locally."
                  : "The analysis engine will prepare when you run."}
          </p>
          <button
            data-testid="run-analysis"
            className="primary run-button"
            onClick={run}
            disabled={
              busy ||
              blocked ||
              !config.series.length ||
              !config.countries.length
            }
            aria-describedby="run-reason"
          >
            Run analysis →
          </button>
          <p id="run-reason" className="small muted">
            {busy
              ? "An operation is running."
              : blocked
                ? `Cannot run yet: ${guidance.join(" ")}`
                : "Configuration roles are ready; data compatibility is checked at estimation."}
          </p>
          <p className="small muted">
            Runs locally in your browser. Actual sample, uncertainty and
            sensitivity accompany every result.
          </p>
          <span className="visually-hidden">
            {number(config.series.length)} selected series
          </span>
        </aside>
      </div>
      {recentResults}
    </section>
  );
}
