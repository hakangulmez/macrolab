import { useState, useSyncExternalStore } from "react";
import type {
  AnalysisConfig,
  AnalysisResult,
  Check,
  CountryResult,
  CountryBundle,
  Manifest,
} from "../types";
import {
  csv,
  download,
  number,
  record,
  records,
  strings,
  text,
} from "../format";
import { Checks, DataTable, Field } from "./Common";
import { Chart } from "./Chart";
import {
  chartData,
  resultTableBlocks,
  analysisCsvRows,
  readingBullets,
  selectedPeakFootnote,
  sensitivityRows,
  shockHeading,
  mobileSummaryLines,
  specificationLabel,
} from "../resultData";
import "../results.css";

interface Props {
  result: AnalysisResult | null;
  manifest: Manifest;
  bundles: Record<string, CountryBundle>;
  busy: boolean;
  rerun: (config: AnalysisConfig) => void;
  exportPython: () => void;
  share: () => void;
  shareUrl: string;
  edit: () => void;
  onSourceCard?: (country: string, conceptId: string) => void;
  previouslyDisplayedChecks?: Check[];
}
const mobileQuery = "(max-width: 760px)";
function subscribeViewport(listener: () => void) {
  const query = window.matchMedia(mobileQuery);
  query.addEventListener("change", listener);
  return () => query.removeEventListener("change", listener);
}
const compactViewport = () => window.matchMedia(mobileQuery).matches;
const serverViewport = () => false;

export function ResultsCountry({
  result,
  manifest,
  comparison,
  first,
  cards,
  compact = false,
  onSourceCard,
  previouslyDisplayedChecks,
}: {
  result: CountryResult;
  manifest: Manifest;
  comparison: boolean;
  first: boolean;
  cards: CountryBundle["cards"];
  compact?: boolean;
  onSourceCard?: (country: string, conceptId: string) => void;
  previouslyDisplayedChecks?: Check[];
}) {
  const indicators = manifest.indicators.map((indicator) => ({
    ...indicator,
    ...cards.find((card) => card.concept_id === indicator.concept_id),
  }));
  const charts = chartData(result, indicators);
  const [variantId, setVariantId] = useState("");
  const [chartName, setChartName] = useState("");
  const selectedChart =
    charts.find((chart) => chart.name === chartName) ?? charts[0];
  const alternatives = result.sensitivity.variants.filter(
    (variant) =>
      variant.variant_id !== "baseline" &&
      variant.status === "available" &&
      records(record(variant.metrics).responses).length,
  );
  const variant =
    alternatives.find((item) => item.variant_id === variantId) ??
    alternatives[0];
  const comparisonLabel = specificationLabel(variant ?? {});
  const sensitivity = result.sensitivity;
  const lagCriteria = record(record(sensitivity).lag_criteria);
  const selectedLags = record(lagCriteria.selected_lags);
  const rows = sensitivityRows(result, indicators);
  const sample = result.actual_sample;
  const name =
    manifest.countries.find((c) => c.iso3 === result.country)?.name ??
    result.country;
  return (
    <section className="stack result-country">
      <div className="row between country-result-heading">
        <h2>{name}</h2>
        <span className="mono">
          {sample.start ?? "No estimate"} → {sample.end ?? "—"} · n ={" "}
          {sample.nobs}
        </span>
      </div>
      <Checks
        showEstimationPhase
        previouslyDisplayedChecks={previouslyDisplayedChecks}
        checks={result.checks}
        onSourceCard={onSourceCard}
        indicators={indicators}
        countries={manifest.countries}
      />
      {result.status === "ok" && (
        <>
          {compact && charts.length > 1 && (
            <Field label="Response chart">
              <select
                data-testid="mobile-chart-selector"
                value={selectedChart?.name}
                onChange={(event) => setChartName(event.target.value)}
              >
                {charts.map((chart) => (
                  <option key={chart.name} value={chart.name}>
                    {chart.name}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {comparison && alternatives.length > 0 && (
            <Field label="Compare response curves with">
              <select
                value={text(variant?.variant_id)}
                onChange={(event) => setVariantId(event.target.value)}
              >
                {alternatives.map((item) => (
                  <option
                    key={text(item.variant_id)}
                    value={text(item.variant_id)}
                  >
                    {specificationLabel(item)}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <div className="legend">
            <span>
              <i className="legend-line" />
              Estimate
            </span>
            {charts.some((chart) =>
              chart.points.some((point) => point.lower !== undefined),
            ) && (
              <span>
                <i className="legend-band" />
                {result.irf
                  ? `${Math.round(result.irf.band_level * 100)}% pointwise interval`
                  : "Coefficient interval"}
              </span>
            )}
            {comparison && variant && (
              <span>
                <i className="legend-line comparison" />
                {comparisonLabel} · point estimate
              </span>
            )}
          </div>
          <div className="charts-grid">
            {charts
              .filter((chart) => !compact || chart.name === selectedChart?.name)
              .map((chart) => {
                const index = charts.indexOf(chart);
                return (
                  <Chart
                    key={chart.name}
                    {...chart}
                    title={chart.name}
                    comparisonLabel={
                      result.irf ? comparisonLabel : "Fitted / trend"
                    }
                    points={chart.points.map((point) => {
                      if (!result.irf) return point;
                      const response = records(
                        record(variant?.metrics).responses,
                      ).find(
                        (item) =>
                          item.variable === result.irf?.variables[index],
                      );
                      const position =
                        (response?.periods as number[] | undefined)?.indexOf(
                          Number(point.period),
                        ) ?? -1;
                      return {
                        ...point,
                        comparison:
                          comparison && position >= 0
                            ? (response?.values as number[])[position]
                            : undefined,
                      };
                    })}
                    first={first && (compact || index === 0)}
                  />
                );
              })}
          </div>
          {!charts.length && (
            <div className="info-box">
              This method returns tables. No continuous response curve is
              defined.
            </div>
          )}
          {result.irf && (
            <p className="small muted peak-footnote">{selectedPeakFootnote}</p>
          )}
          <div className="result-grid">
            <section className="card stack sensitivity-section">
              <h2>How much does the answer depend on the model?</h2>
              {comparison ? (
                <>
                  <p className="small muted">
                    {result.irf
                      ? "Signed ranges include the baseline and comparable specifications, using each curve's largest absolute response. Signs are compared at the baseline peak horizon."
                      : "Compare estimates and sign agreement across the available specifications."}
                  </p>
                  {rows.length ? (
                    compact ? (
                      <div
                        className="sensitivity-cards"
                        data-testid="mobile-sensitivity-cards"
                      >
                        {rows.map((row, index) => (
                          <details
                            key={index}
                            className="sensitivity-mini-card"
                          >
                            <summary>
                              <strong>{text(row.Response ?? row.Term)}</strong>
                              <span>
                                {text(
                                  row["Baseline peak"] ??
                                    row["Baseline estimate"],
                                )}
                              </span>
                            </summary>
                            <dl>
                              {Object.entries(row)
                                .filter(
                                  ([key]) =>
                                    !["Response", "Term"].includes(key),
                                )
                                .map(([key, value]) => (
                                  <div key={key}>
                                    <dt>{key}</dt>
                                    <dd>{text(value)}</dd>
                                  </div>
                                ))}
                            </dl>
                          </details>
                        ))}
                      </div>
                    ) : (
                      <DataTable rows={rows} />
                    )
                  ) : (
                    <p>
                      {text(
                        sensitivity.reason,
                        "Sensitivity is not applicable to this output.",
                      )}
                    </p>
                  )}
                  <details className="specification-details">
                    <summary>Every specification and its sample</summary>
                    <div className="stack">
                      {sensitivity.variants.map((v, index) => {
                        const s = record(v.sample ?? v.actual_sample);
                        return (
                          <div key={index}>
                            <strong>{specificationLabel(v)}</strong> ·{" "}
                            {text(v.status)}
                            <p className="small">
                              {strings(v.changes).join("; ")}{" "}
                              {text(v.reason, "")}
                            </p>
                            <p className="mono">
                              {text(s.start)}–{text(s.end)} · n {text(s.nobs)}
                            </p>
                            {records(v.checks).map((check, i) => (
                              <p className="small" key={i}>
                                {text(check.message)}
                              </p>
                            ))}
                            {Object.keys(record(v.metrics)).length > 0 && (
                              <details>
                                <summary>Variant estimates</summary>
                                <DataTable
                                  rows={records(
                                    record(v.metrics).responses ??
                                      record(v.metrics).coefficients,
                                  )}
                                />
                              </details>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </details>
                </>
              ) : (
                <p className="muted">
                  Turn on specification comparison to inspect sensitivity.
                </p>
              )}
              {comparison && Object.keys(lagCriteria).length > 0 && (
                <details className="lag-criteria-details">
                  <summary>
                    Lag selection · AIC {text(selectedLags.aic)} · BIC{" "}
                    {text(selectedLags.bic)} · HQIC {text(selectedLags.hqic)}
                  </summary>
                  <p className="small">
                    {text(
                      lagCriteria.interpretation ?? lagCriteria.reason,
                      "Criteria use a common comparison sample; the baseline lag remains unchanged.",
                    )}
                  </p>
                  <p className="small mono">
                    Comparison sample:{" "}
                    {text(record(lagCriteria.comparison_sample).start)}–
                    {text(record(lagCriteria.comparison_sample).end)} · n ={" "}
                    {text(record(lagCriteria.comparison_sample).nobs)}
                  </p>
                  <DataTable
                    rows={records(lagCriteria.candidates).map((candidate) => ({
                      Lag: candidate.lag,
                      AIC: candidate.aic,
                      BIC: candidate.bic,
                      HQIC: candidate.hqic,
                    }))}
                  />
                </details>
              )}
            </section>
            <aside className="card stack reading">
              <h2>Reading the result</h2>
              <ul data-testid="reading-bullets">
                {readingBullets(result, indicators).map((bullet, index) => (
                  <li key={index}>{bullet}</li>
                ))}
              </ul>
            </aside>
          </div>
          <details className="card technical-details">
            <summary>Tables, diagnostics and full method notes</summary>
            <div className="stack">
              {resultTableBlocks(result).map((block) => (
                <details
                  key={block.title}
                  open={block.title.includes("Test") || !charts.length}
                >
                  <summary>{block.title}</summary>
                  <DataTable rows={block.rows} columns={block.columns} />
                </details>
              ))}
              {Boolean(result.fevd) && (
                <details>
                  <summary>Forecast-error variance decomposition</summary>
                  <p className="small">
                    Shares by response, horizon and identified shock. Point
                    estimates only.
                  </p>
                  <DataTable
                    rows={(() => {
                      const f = record(result.fevd);
                      return ((f.values as number[][][]) ?? []).flatMap(
                        (h, i) =>
                          h.flatMap((v, j) =>
                            v.map((value, k) => ({
                              horizon: (f.periods as number[])[i],
                              response: (f.variables as string[])[j],
                              shock: (f.shocks as string[])[k],
                              share: value,
                            })),
                          ),
                      );
                    })()}
                  />
                </details>
              )}
              <details>
                <summary>Actual sample, conversions and diagnostics</summary>
                <p>
                  {sample.nobs} estimation observations from{" "}
                  {sample.common_nobs} complete common observations.{" "}
                  {sample.dropped_periods.length} requested periods dropped.
                </p>
                <DataTable rows={sample.dropped_periods} />
                <h3>Frequency conversions</h3>
                <DataTable
                  rows={Object.entries(sample.frequency_conversion).map(
                    ([concept, value]) => ({ concept, ...record(value) }),
                  )}
                />
                <h3>Transformations</h3>
                <DataTable
                  rows={Object.entries(sample.transforms).map(
                    ([concept, value]) => ({ concept, ...record(value) }),
                  )}
                />
                <h3>Diagnostics</h3>
                <DataTable
                  rows={Object.entries(result.diagnostics ?? {})
                    .filter(([, value]) => typeof value !== "object")
                    .map(([diagnostic, value]) => ({ diagnostic, value }))}
                />
              </details>
              <details>
                <summary>Full method notes and sensitivity definition</summary>
                {strings(result.notes).map((note, index) => (
                  <p key={index}>{note}</p>
                ))}
                <p>{sensitivity.comparison_rule}</p>
                {strings(sensitivity.limitations).map((note, index) => (
                  <p key={index}>{note}</p>
                ))}
              </details>
            </div>
          </details>
        </>
      )}
    </section>
  );
}

export function Results({
  result,
  manifest,
  bundles,
  busy,
  rerun,
  exportPython,
  share,
  shareUrl,
  edit,
  onSourceCard,
  previouslyDisplayedChecks,
}: Props) {
  const [comparison, setComparison] = useState(true);
  const compact = useSyncExternalStore(
    subscribeViewport,
    compactViewport,
    serverViewport,
  );
  if (!result)
    return (
      <section data-testid="screen-results" className="card empty">
        <h1>Your results will appear here</h1>
        <p>Select a template, review its inputs and run the analysis.</p>
        <button className="primary" onClick={edit}>
          Build an analysis
        </button>
      </section>
    );
  const irf = result.results.find((r) => r.irf)?.irf;
  const config = result.config;
  const model = manifest.models.find((m) => m.id === config.model.id);
  const policyShock =
    irf && ["policy_rate", "us_policy_rate"].includes(irf.shock);
  const shockUnits = policyShock ? "pp" : "transformed units";
  function shock(mode: string, size: number) {
    const next = structuredClone(config);
    next.outputs.irf = {
      ...next.outputs.irf!,
      shock_mode: mode,
      shock_size: size,
    };
    rerun(next);
  }
  function precision(draws: number) {
    const next = structuredClone(config);
    next.outputs.irf = { ...next.outputs.irf!, method: "bootstrap", draws };
    rerun(next);
  }
  const exportCsv = () => {
    const rows = analysisCsvRows(result);
    const columns = Array.from(new Set(rows.flatMap(Object.keys)));
    download(
      csv([
        columns,
        ...rows.map((row) =>
          columns.map((key) => row[key as keyof typeof row]),
        ),
      ]),
      "macrolab-results.csv",
      "text/csv",
    );
  };
  return (
    <section data-testid="screen-results" className="stack results-screen">
      {compact && (
        <div
          className="mobile-result-summary"
          data-testid="mobile-result-summary"
          aria-label="Result summary"
        >
          {mobileSummaryLines(result).map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </div>
      )}
      <div className="row between result-actions">
        <button className="link" onClick={edit}>
          ← Edit this analysis
        </button>
        <div className="results-toolbar">
          <button
            data-testid="export-png"
            disabled={
              !result.results.some((r) =>
                chartData(r, manifest.indicators).some((c) => c.points.length),
              )
            }
            onClick={() =>
              window.dispatchEvent(new Event("macrolab-export-png"))
            }
          >
            Export PNG
          </button>
          <button data-testid="export-csv" onClick={exportCsv}>
            Download CSV
          </button>
          <button
            data-testid="export-python"
            disabled={busy || result.status !== "ok"}
            onClick={exportPython}
          >
            Python script
          </button>
          <button data-testid="share-link" disabled={busy} onClick={share}>
            Share link
          </button>
        </div>
      </div>
      <div className="result-heading">
        <div>
          <span className="overline">Results · {model?.title}</span>
          <h1>
            {irf
              ? shockHeading(irf, config, manifest.indicators)
              : `${model?.title ?? config.model.id}: the estimated relationship`}
          </h1>
          <p className="muted">
            {config.countries
              .map(
                (c) => manifest.countries.find((x) => x.iso3 === c)?.name ?? c,
              )
              .join(" · ")}{" "}
            ·{" "}
            {config.frequency === "Q"
              ? "Quarterly"
              : config.frequency === "M"
                ? "Monthly"
                : "Annual"}{" "}
            ·{" "}
            {irf
              ? `${Math.round(irf.band_level * 100)}% pointwise bands`
              : config.model.id.startsWith("sing.")
                ? `${Math.round((config.outputs.confidence ?? 0.95) * 100)}% coefficient intervals`
                : "Descriptive output; see method assumptions"}
          </p>
          <div className="result-meta">
            <span>Snapshot {result.snapshot_id}</span>
            <span>Code {result.code_version}</span>
            <span>{number(result.runtime_ms, 0)} ms</span>
            <span title={result.config_hash}>
              Config {result.config_hash.slice(0, 12)}
            </span>
          </div>
        </div>
        {irf && (
          <details className="card result-controls" open={!compact}>
            <summary>Shock size and interval precision</summary>
            <div className="stack">
              <Field label={policyShock ? "Policy shock" : "Shock size"}>
                <select
                  disabled={busy}
                  value={
                    config.outputs.irf?.shock_mode === "one_sd"
                      ? "sd"
                      : String(config.outputs.irf?.shock_size)
                  }
                  onChange={(e) =>
                    shock(
                      e.target.value === "sd" ? "one_sd" : "fixed",
                      e.target.value === "sd" ? 1 : Number(e.target.value),
                    )
                  }
                >
                  <option value="sd">One identified standard deviation</option>
                  <option value="0.25">
                    {policyShock ? "+25 bp" : "+0.25 transformed units"}
                  </option>
                  <option value="1">
                    {policyShock ? "+1 pp" : "+1 transformed unit"}
                  </option>
                  {!["sd", "0.25", "1"].includes(
                    config.outputs.irf?.shock_mode === "one_sd"
                      ? "sd"
                      : String(config.outputs.irf?.shock_size),
                  ) && (
                    <option value={String(config.outputs.irf?.shock_size)}>
                      Custom shock
                    </option>
                  )}
                </select>
              </Field>
              <Field label={`Custom shock (${shockUnits}; release to rerun)`}>
                <input
                  disabled={busy}
                  type="range"
                  min="-2"
                  max="2"
                  step="0.25"
                  key={irf.shock_size}
                  defaultValue={irf.shock_size}
                  onPointerUp={(e) => {
                    const value = Number(e.currentTarget.value);
                    if (value !== 0) shock("fixed", value);
                  }}
                  onKeyUp={(e) => {
                    if (
                      ["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                        e.key,
                      ) &&
                      Number(e.currentTarget.value) !== 0
                    )
                      shock("fixed", Number(e.currentTarget.value));
                  }}
                />
              </Field>
              <Field label="Bootstrap precision">
                <select
                  data-testid="bootstrap-precision"
                  disabled={busy}
                  value={String(config.outputs.irf?.draws)}
                  onChange={(event) => precision(Number(event.target.value))}
                >
                  <option value="200">Interactive · 200 draws</option>
                  <option value="1000">Precise · 1,000 draws</option>
                  {![200, 1000].includes(config.outputs.irf?.draws ?? 0) && (
                    <option value={config.outputs.irf?.draws}>
                      Current · {number(config.outputs.irf?.draws, 0)} draws
                    </option>
                  )}
                </select>
              </Field>
              <p className="small muted">
                Precision changes rerun the seeded bootstrap. Slider limits do
                not establish historical support.
              </p>
            </div>
          </details>
        )}
      </div>
      <div
        role="status"
        data-testid="result-status"
        data-config-hash={result.config_hash}
        data-snapshot-id={result.snapshot_id}
        data-model-id={config.model.id}
        data-result-status={result.status}
        className={result.status === "ok" ? "info-box" : "error-box"}
      >
        <strong>
          {result.status === "ok"
            ? "Analysis complete"
            : "Analysis blocked or partly unavailable"}
        </strong>{" "}
        · {result.label}
      </div>
      {shareUrl && (
        <Field label="Local share link">
          <input
            data-testid="share-url"
            readOnly
            value={shareUrl}
            onFocus={(e) => e.currentTarget.select()}
          />
        </Field>
      )}
      <div className="row comparison-control">
        <label className="row">
          <input
            type="checkbox"
            checked={comparison}
            onChange={(e) => setComparison(e.target.checked)}
          />
          Compare specifications
        </label>
        <span className="small muted">
          Exact samples and assumptions remain available below.
        </span>
      </div>
      {result.results.map((r, index) => (
        <ResultsCountry
          key={r.country}
          result={r}
          manifest={manifest}
          comparison={comparison}
          first={
            index ===
            result.results.findIndex(
              (item) =>
                item.status === "ok" &&
                chartData(item, manifest.indicators).some(
                  (chart) => chart.points.length,
                ),
            )
          }
          cards={bundles[r.country]?.cards ?? []}
          compact={compact}
          onSourceCard={onSourceCard}
          previouslyDisplayedChecks={previouslyDisplayedChecks}
        />
      ))}
    </section>
  );
}
