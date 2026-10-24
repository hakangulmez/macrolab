import { useContext, useEffect, useRef, useState } from "react";
import { ChartExportContext } from "../chartExportContext";
import { AnalysisRuntime, buildBundle } from "../runtime";
import type {
  AnalysisConfig,
  CountryResult,
  IRF,
  JsonRecord,
  Manifest,
  Card,
  Check,
} from "../types";
import {
  csv,
  download,
  number,
  significant,
  record,
  records,
  text,
  title,
} from "../format";
import { countryIndicators } from "../displayLabels";
import { chartData, type ResultChart } from "../resultData";
import { exportPng } from "../pngExport";
import { Chart } from "./Chart";
import { Checks, DataTable, Field } from "./Common";

export function MethodComparison({
  config,
  result,
  manifest,
  runtime,
  busy,
  cards,
  compact,
}: {
  config: AnalysisConfig;
  result: CountryResult;
  manifest: Manifest;
  runtime: AnalysisRuntime;
  busy: boolean;
  cards: Card[];
  compact: boolean;
}) {
  const exportContext = useContext(ChartExportContext);
  const responses = (result.irf?.variables ?? []).filter(
    (v) => v !== result.irf?.shock,
  );
  const [response, setResponse] = useState(responses[0]);
  const [mode, setMode] = useState("both");
  const [pair, setPair] = useState<JsonRecord | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const indicators = countryIndicators(manifest.indicators, result.country);
  async function compute(exportScript = false) {
    setPending(true);
    setError("");
    try {
      const bundle = await buildBundle(config);
      if (exportScript) {
        const script = await runtime.exportMethods(
          config,
          bundle,
          response,
          result.country,
        );
        if (alive.current)
          download(
            script,
            `macrolab-${result.country}-${response}-methods.py`,
            "text/x-python",
          );
      } else {
        const next = await runtime.compareMethods(
          config,
          bundle,
          response,
          result.country,
        );
        if (alive.current) setPair(next);
      }
    } catch (e) {
      if (alive.current) setError(String(e));
    } finally {
      if (alive.current) setPending(false);
    }
  }
  const varIRF = record(pair?.var).irf as IRF | undefined;
  const lpIRF = record(pair?.lp).irf as IRF | undefined;
  const irf = mode === "LP" ? lpIRF : varIRF;
  const base = chartData(result, indicators).find(
    (c) => c.variable === response,
  );
  const sample = record(pair?.sample);
  const comparison = record(pair?.comparison);
  const points =
    irf?.periods.map((h, i) => ({
      period: h,
      value: irf.values[i][0],
      lower: irf.lower[i][0],
      upper: irf.upper[i][0],
      comparison: mode === "both" ? lpIRF?.values[i][0] : undefined,
      comparisonLower: mode === "both" ? lpIRF?.lower[i][0] : undefined,
      comparisonUpper: mode === "both" ? lpIRF?.upper[i][0] : undefined,
    })) ?? [];
  const chart: ResultChart = {
    name: `${title(response, indicators)} · ${mode === "both" ? "VAR and LP" : mode}`,
    points,
    unit: base?.unit ?? "response units",
    transformation: base?.transformation,
    summary: `Same recursive shock and ${sample.nobs} estimation dates. Bands are pointwise and use different inference: VAR residual bootstrap; LP conditional HC1.`,
  };
  const rows = records(comparison.horizons).map((r) => ({
    Horizon: r.horizon,
    VAR: significant(r.var),
    LP: significant(r.lp),
    "Same sign": r.sign_agreement ? "Yes" : "No",
    "Bands overlap": r.band_overlap ? "Yes" : "No",
  }));
  const summary = ["var", "lp"].map((method) => {
    const peak = record(comparison[`${method}_peak`]);
    return {
      Method: method.toUpperCase(),
      "Peak response": significant(peak[method]),
      "Peak horizon": peak.horizon,
      Sample: `${sample.start}–${sample.end}`,
      Observations: sample.nobs,
      Identification: "Same recursive innovation within this pair",
      "Baseline agreement count": "Excluded",
    };
  });
  return (
    <section
      className="card stack method-comparison"
      data-testid="method-comparison"
    >
      <h2>VAR / LP · matched method comparison</h2>
      <p className="small">
        Compute a separate comparison on identical estimation dates and one
        recursive innovation. This refits a shorter window to allow LP future
        outcomes.{" "}
        {config.model.id === "lp.ols" &&
          "The recursive innovation differs from the raw-impulse baseline. "}
        The baseline and its agreement counts stay separate.
      </p>
      <div className="row">
        <Field label="Method comparison response">
          <select
            aria-label="Method comparison response"
            value={response}
            disabled={pending}
            onChange={(e) => {
              setResponse(e.target.value);
              setPair(null);
            }}
          >
            {responses.map((v) => (
              <option key={v} value={v}>
                {title(v, indicators)}
              </option>
            ))}
          </select>
        </Field>
        <button disabled={busy || pending} onClick={() => void compute()}>
          {pending
            ? "Computing matched comparison…"
            : "Compute matched VAR / LP"}
        </button>
        {pending && (
          <button onClick={() => runtime.cancel()}>Cancel comparison</button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {pair?.status === "blocked" && (
        <p role="alert">Comparison blocked: {text(pair.reason)}</p>
      )}
      {pair?.status === "ok" && (
        <>
          <Checks
            checks={(pair.checks ?? []) as Check[]}
            indicators={indicators}
            countries={manifest.countries}
          />
          <div className="row" role="group" aria-label="Response method">
            {["VAR", "LP", "both"].map((m) => (
              <button
                key={m}
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
              >
                {m}
              </button>
            ))}
          </div>
          <p className="mono small">
            Actual common sample: {text(sample.start)}–{text(sample.end)} · n ={" "}
            {text(sample.nobs)} · shock{" "}
            {number(record(pair.shock).physical_size, 3)} · largest root{" "}
            {number(record(record(pair.var).diagnostics).largest_root, 4)}
          </p>
          <div className="legend">
            <span>
              <i className="legend-line" />
              {mode === "LP" ? "LP · HC1" : "VAR · residual bootstrap"} · 68%
              pointwise band
            </span>
            {mode === "both" && (
              <span>
                <i className="legend-line comparison" />
                LP · conditional HC1 · 68% pointwise band
              </span>
            )}
          </div>
          <Chart
            {...chart}
            title={chart.name}
            comparisonLabel="LP"
            exportContext={
              exportContext && {
                ...exportContext,
                analysis: "Matched VAR / LP",
                country:
                  manifest.countries.find((c) => c.iso3 === result.country)
                    ?.name ?? result.country,
                sample: `Actual common sample: ${sample.start}–${sample.end} · n = ${sample.nobs} · Snapshot ${config.snapshot_id}`,
                estimateLabel: mode === "LP" ? "LP" : "VAR",
              }
            }
          />
          <h3>Sensitivity · method comparison only</h3>
          {compact ? (
            <div className="sensitivity-cards">
              {summary.map((row) => (
                <article key={row.Method} className="sensitivity-mini-card">
                  <strong>
                    {row.Method} · {text(row["Peak response"])} at horizon{" "}
                    {text(row["Peak horizon"])}
                  </strong>
                  <p className="small">
                    {row.Sample} · n = {text(row.Observations)}
                  </p>
                  <p className="small">
                    Same recursive innovation within this pair. Excluded from
                    baseline agreement.
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <DataTable rows={summary} />
          )}
          <p className="small">
            Within-pair sign agreement:{" "}
            {
              records(comparison.horizons).filter((r) => r.sign_agreement)
                .length
            }
            /{rows.length} horizons. Band overlap:{" "}
            {records(comparison.horizons).filter((r) => r.band_overlap).length}/
            {rows.length}. These are descriptive counts; estimates are never
            averaged.
          </p>
          <details>
            <summary>
              Every horizon, dates, dropped periods and shock definition
            </summary>
            <DataTable rows={rows} />
            <pre>
              {JSON.stringify(
                {
                  sample: pair.sample,
                  shock: {
                    ...record(pair.shock),
                    values: "Included at full precision in the JSON export",
                  },
                  shock_fingerprint: pair.shock_fingerprint,
                },
                null,
                2,
              )}
            </pre>
          </details>
          <p className="small muted">{text(pair.note)}</p>
          <div className="row">
            <button
              onClick={() => {
                const raw = records(comparison.horizons).map((r) => ({
                  country: result.country,
                  response,
                  baseline_config_hash: pair.baseline_config_hash,
                  sample_start: sample.start,
                  sample_end: sample.end,
                  nobs: sample.nobs,
                  dropped_periods: sample.dropped_periods,
                  frequency_conversion: sample.frequency_conversion,
                  physical_shock: record(pair.shock).physical_size,
                  identification: comparison.label,
                  included_in_baseline_agreement: false,
                  ...r,
                }));
                download(
                  csv([
                    Object.keys(raw[0]),
                    ...raw.map((r) => Object.values(r)),
                  ]),
                  `macrolab-${result.country}-${response}-methods.csv`,
                  "text/csv",
                );
              }}
            >
              Comparison CSV
            </button>
            <button
              onClick={() =>
                download(
                  JSON.stringify(pair, null, 2),
                  `macrolab-${result.country}-${response}-methods.json`,
                  "application/json",
                )
              }
            >
              Comparison JSON
            </button>
            <button
              disabled={busy || pending}
              onClick={() => void compute(true)}
            >
              Comparison Python
            </button>
            <button
              onClick={() =>
                void exportPng([chart], {
                  snapshot: config.snapshot_id,
                  analysis: "Matched VAR / LP",
                  country: result.country,
                  sample: `Actual common sample: ${sample.start}–${sample.end} · n = ${sample.nobs}`,
                  sources: [
                    ...new Set(
                      cards
                        .filter((c) =>
                          config.series.some(
                            (s) => s.concept_id === c.concept_id,
                          ),
                        )
                        .flatMap((c) =>
                          records(c.source_segments).map((s) => text(s.source)),
                        ),
                    ),
                  ],
                  frequency: config.frequency,
                  horizon: true,
                  bandLevel: 0.68,
                  comparisonLabel: "LP · conditional HC1",
                  estimateLabel: mode === "LP" ? "LP" : "VAR",
                  note: "Separate matched-window comparison; excluded from baseline agreement counts.",
                }).catch((e) => setError(String(e)))
              }
            >
              Comparison PNG
            </button>
          </div>
        </>
      )}
    </section>
  );
}
