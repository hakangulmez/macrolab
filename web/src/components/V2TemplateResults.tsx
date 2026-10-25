import { sensitivityDisplayLabel } from "../sensitivityLabels";
import { useContext, useEffect, useState } from "react";
import type { AnalysisResult, Manifest } from "../types";
import { records, strings, text, record } from "../format";
import { Checks, DataTable, Field } from "./Common";
import { PanelResults } from "./PanelResults";
import { ForecastResults } from "./ForecastResults";
import { chartData, termLabel } from "../resultData";
import { ChartExportContext } from "../chartExportContext";
import { exportPng } from "../pngExport";
import { countryIndicators } from "../displayLabels";

import { v2Template } from "../templatesV2";

export function V2TemplateResults({
  result,
  manifest,
}: {
  result: AnalysisResult;
  manifest: Manifest;
}) {
  const [outcome, setOutcome] = useState("cpi");
  const [country, setCountry] = useState("DEU");
  const [exportError, setExportError] = useState("");
  const context = useContext(ChartExportContext);
  const id = result.config.model.params.template_id;
  useEffect(() => {
    if (
      !context ||
      !["ea_phillips_pooled", "same_ecb_shock_pooled"].includes(String(id))
    )
      return;
    const handler = (event: Event) => {
      const all = result.results.flatMap((r) =>
        chartData(
          r,
          id === "ea_phillips_pooled"
            ? manifest.indicators.map((i) =>
                i.concept_id === "unemp"
                  ? { ...i, title: "Unemployment gap (HP, λ = 1600)" }
                  : i,
              )
            : countryIndicators(manifest.indicators, "EA"),
        ).map((chart) =>
          id !== "same_ecb_shock_pooled"
            ? chart
            : {
                ...chart,
                name:
                  chart.variable === "cpi"
                    ? "HICP · headline prices"
                    : chart.name,
                points: chart.points.map((p, i) => ({
                  ...p,
                  comparison: Number(
                    records(record(record(r.panel).country_estimates)[country])[
                      i
                    ]?.estimate,
                  ),
                })),
              },
        ),
      );
      const panels =
        (event as CustomEvent<{ mode?: string }>).detail?.mode === "panel";
      const selected = panels
        ? all
        : [all.find((c) => c.variable === outcome) ?? all[0]];
      setExportError("");
      void exportPng(selected, {
        ...context,
        intervalLabel:
          id === "same_ecb_shock_pooled"
            ? "68% pointwise band"
            : "95% confidence interval (Driscoll–Kraay)",
        note: strings(result.template_notes)[0],
        ...(id === "same_ecb_shock_pooled"
          ? {
              comparisonLabel: `${manifest.countries.find((c) => c.iso3 === country)?.name ?? country} · matched sample`,
              sample: `Snapshot ${result.snapshot_id} · ${result.results.map((r) => `${r.outcome === "cpi" ? "HICP" : "GDP"}: ${r.actual_sample.start}–${r.actual_sample.end}, n=${r.actual_sample.nobs}`).join("; ")}`,
            }
          : {}),
      }).catch((e) => setExportError(String(e)));
    };
    window.addEventListener("macrolab-export-png", handler);
    return () => window.removeEventListener("macrolab-export-png", handler);
  }, [
    context,
    id,
    result,
    manifest.indicators,
    manifest.countries,
    outcome,
    country,
  ]);
  if (!v2Template(id)) return null;
  const lp = id === "same_ecb_shock_pooled",
    fe = id === "ea_phillips_pooled";
  const row =
    result.results.find((r) => r.outcome === outcome) ?? result.results[0];
  const evaluation = record(row.evaluation);
  const origins = records(evaluation.origins);
  const display = fe
    ? {
        ...manifest,
        indicators: manifest.indicators.map((i) =>
          i.concept_id === "unemp"
            ? {
                ...i,
                title: "Unemployment gap (HP, λ = 1600)",
              }
            : i,
        ),
      }
    : manifest;
  return (
    <section className="stack" data-testid="v2-template-results">
      {exportError && <p role="alert">{exportError}</p>}
      <section className="card stack">
        <h2>Specification and interpretation</h2>
        {strings(result.template_notes).map((note) => (
          <p key={note}>{note}</p>
        ))}
        {!fe && !lp && origins.length > 0 && (
          <p>
            First training window: {text(origins[0].training_start)}–
            {text(origins[0].training_end)}, {text(origins[0].training_nobs)}{" "}
            observations. Last origin: {text(origins.at(-1)?.origin)}. The input
            window also includes 1998 observations used only to initialise
            year-on-year changes; they are not training observations. Every
            origin’s exact sample is in details and exports.
          </p>
        )}
        {lp && (
          <p>
            ECB DFR shock: +{Number(row.irf?.shock_size).toPrecision(3)} pp (one
            standard deviation).
          </p>
        )}
      </section>
      {lp && (
        <Field label="Pooled outcome">
          <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="cpi">
              HICP · cumulative % change in the price level
            </option>
            <option value="gdp_real">
              Real GDP · cumulative % change in the level
            </option>
          </select>
        </Field>
      )}
      {fe || lp ? (
        <PanelResults
          key={outcome}
          result={row}
          manifest={display}
          selectedCountry={lp ? country : undefined}
          onCountryChange={lp ? setCountry : undefined}
        />
      ) : (
        <ChartExportContext.Provider
          value={
            context
              ? {
                  ...context,
                  sample: `Snapshot ${result.snapshot_id} · Initial training: ${text(origins[0]?.training_start)}–${text(origins[0]?.training_end)}, n=${text(origins[0]?.training_nobs)}; expanding through ${text(origins.at(-1)?.origin)}. 1998 input observations initialise changes only.`,
                }
              : context
          }
        >
          <ForecastResults result={row} manifest={manifest} first />
        </ChartExportContext.Provider>
      )}
      {(fe || lp) && (
        <section className="card stack" data-testid="v2-template-sensitivity">
          <h2>Specification sensitivity</h2>
          <p className="small">
            “Changes the answer materially” means a sign flip or a change
            greater than 50% from baseline at the same horizon or coefficient.
            This is descriptive, not a significance test. Alternative gaps and
            pooled restrictions can change the estimand; no agreement count is
            reported.
          </p>
          {records(result.template_sensitivity).map((variant) => {
            const comparison = records(variant.comparison).filter(
              (r) => !lp || r.outcome === outcome,
            );
            const material = comparison.filter((r) => r.material);
            const shown = lp
              ? comparison.filter((r) =>
                  [0, 4, 8, 12, 20].includes(Number(r.horizon)),
                )
              : comparison;
            return (
              <details key={text(variant.id)}>
                <summary>
                  {sensitivityDisplayLabel(variant)} ·{" "}
                  {variant.status === "ok"
                    ? material.length
                      ? "changes the answer materially"
                      : "within the descriptive threshold"
                    : text(variant.status)}
                </summary>
                {lp && (
                  <p className="small">
                    Shock: +
                    {Number(
                      record(records(variant.results)[0]?.irf).shock_size,
                    ).toPrecision(3)}{" "}
                    pp (one SD in this specification). Anchor sample:{" "}
                    {text(
                      record(records(variant.results)[0]?.actual_sample).start,
                    )}
                    –
                    {text(
                      record(records(variant.results)[0]?.actual_sample).end,
                    )}
                    .
                  </p>
                )}
                {lp && material.length > 0 && (
                  <p className="small">
                    Material changes at horizons{" "}
                    {material.map((r) => text(r.horizon)).join(", ")}.
                  </p>
                )}
                <DataTable
                  caption={`${lp ? "68% pointwise intervals" : "95% confidence intervals"} · ${text(record(record(variant.config).model).id)} · ${text(record(record(record(variant.config).model).params).covariance)}`}
                  rows={shown.map((r) => ({
                    [lp ? "Horizon" : "Term"]: lp
                      ? r.horizon
                      : termLabel(text(r.term), display.indicators),
                    Baseline: r.baseline,
                    Estimate: r.estimate,
                    Lower: r.lower,
                    Upper: r.upper,
                    "Material change": r.material ? "Yes" : "No",
                  }))}
                />
                <Checks
                  countries={manifest.countries}
                  checks={(variant.checks ?? []) as AnalysisResult["checks"]}
                />
                <details>
                  <summary>Exact specification, sample and full result</summary>
                  <pre>{JSON.stringify(variant, null, 2)}</pre>
                </details>
              </details>
            );
          })}
        </section>
      )}
    </section>
  );
}
