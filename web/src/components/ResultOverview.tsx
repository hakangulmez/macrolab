import { ResultDataTable as DataTable } from "./ResultDataTable";
import { robustnessHeadlines } from "../resultFacts";
import {
  parameterDisplayLabel,
  resultDisplayLabel,
  screenText,
} from "../chartDisplay";
import { sensitivityDisplayLabel } from "../sensitivityLabels";
import type { AnalysisResult, Manifest, Check } from "../types";
import { records, record, significant, text } from "../format";
import { chartData, termLabel } from "../resultData";
import { countryIndicators } from "../displayLabels";
import { templateTags } from "../uiData";
import {
  distinctFindings,
  warningTiers,
  readableCheckMessage,
  resultDisclosureChecks,
} from "./warnings";
function resultName(result: AnalysisResult, manifest: Manifest) {
  const config = result.config;
  const template =
    manifest.templates.find((t) => t.id === config.model.params.template_id) ??
    manifest.templates.find(
      (t) =>
        t.config.model.id === config.model.id &&
        t.config.countries.join() === config.countries.join() &&
        t.config.series.map((s) => s.concept_id).join() ===
          config.series.map((s) => s.concept_id).join(),
    );
  return {
    title:
      template?.title ??
      manifest.models.find((m) => m.id === config.model.id)?.title ??
      config.model.id,
    method: template
      ? templateTags[template.id]
      : (manifest.models.find((m) => m.id === config.model.id)?.title ??
        config.model.id),
  };
}
export function ResultOverview({
  result,
  manifest,
  edit,
  numbersOnly = false,
  hideNumbers = false,
  conciseNumbers = false,
}: {
  result: AnalysisResult;
  manifest: Manifest;
  edit: () => void;
  numbersOnly?: boolean;
  hideNumbers?: boolean;
  conciseNumbers?: boolean;
}) {
  const r = result.results[0],
    title = resultName(result, manifest),
    charts = r
      ? chartData(
          r,
          countryIndicators(manifest.indicators, result.config.countries[0]),
        )
      : [];
  const primary = charts[0];
  const values =
    primary?.points.filter((p) => typeof p.value === "number") ?? [];
  const peak = values.reduce<(typeof values)[0] | undefined>(
    (a, b) => (!a || Math.abs(b.value!) > Math.abs(a.value!) ? b : a),
    undefined,
  );
  const pass = records(record(r?.pass_through).horizons).find(
    (h) => h.horizon === 12,
  );
  const metric = records(record(r?.evaluation).metrics)
    .filter((m) => m.horizon === 1 && typeof m.rmse === "number")
    .reduce<Record<string, unknown> | undefined>(
      (best, m) => (!best || Number(m.rmse) < Number(best.rmse) ? m : best),
      undefined,
    );
  const panel = record(r?.panel);
  const coef = r?.coefficients_table?.find(
    (c) => !["const", "intercept"].includes(c.term),
  );
  const kpis: [string, string, string][] = pass
    ? [
        [
          "12-month ratio",
          significant(pass.ratio),
          "Cumulative CPI / cumulative NEER",
        ],
        [
          "6-month ratio",
          significant(
            records(record(r.pass_through).horizons).find(
              (h) => h.horizon === 6,
            )?.ratio,
          ),
          "Same impulse",
        ],
        [
          "24-month ratio",
          significant(
            records(record(r.pass_through).horizons).find(
              (h) => h.horizon === 24,
            )?.ratio,
          ),
          "Same impulse",
        ],
      ]
    : metric
      ? [
          ["Lowest RMSE · h = 1", text(metric.model), "Paired common origins"],
          ["RMSE", significant(metric.rmse), "Original units of the target"],
          [
            "Relative RMSE",
            significant(metric.relative_rmse),
            "Random walk = 1",
          ],
        ]
      : r?.irf && peak
        ? [
            [`${primary.name} peak`, significant(peak.value), primary.unit],
            [
              "Peak horizon",
              String(peak.period),
              result.config.frequency === "M"
                ? "Months after shock"
                : "Quarters after shock",
            ],
            [
              "Shock size",
              significant(r.irf.shock_size),
              r.irf.shock === "policy_rate"
                ? "Percentage points"
                : "As specified",
            ],
          ]
        : coef
          ? [
              [
                "Estimate",
                significant(coef.estimate),
                termLabel(coef.term, manifest.indicators),
              ],
              [
                "Standard error",
                significant(coef.std_error),
                parameterDisplayLabel(
                  text(panel.covariance, "Reported covariance"),
                ),
              ],
              [
                "Reported interval",
                `${significant(coef.lower)} to ${significant(coef.upper)}`,
                "Reported coefficient bounds",
              ],
            ]
          : [
              ["Method", title.method, "Existing validated output"],
              ["Status", result.status, "See assumptions and checks"],
            ];
  kpis.push([
    "Observations",
    text(r?.actual_sample.nobs),
    r?.actual_sample.start && r.actual_sample.end
      ? `${r.actual_sample.start} → ${r.actual_sample.end}`
      : "No estimation sample",
  ]);
  const numbers = (
    <dl className="result-kpis">
      {(conciseNumbers
        ? kpis
            .filter(
              ([label]) => !["Standard error", "Observations"].includes(label),
            )
            .slice(0, 2)
        : kpis
      ).map(([label, value, note]) => (
        <div key={label} data-metric={label}>
          <dt>{label}</dt>
          <dd>
            {value}
            <small>{note}</small>
          </dd>
        </div>
      ))}
    </dl>
  );
  if (numbersOnly) return numbers;
  return (
    <header className="result-overview">
      <p className="breadcrumbs">
        <button className="link" onClick={edit}>
          Build
        </button>
        <span aria-hidden="true">/</span> Results
      </p>
      <p className="overline">{title.method}</p>
      <h1>{title.title}</h1>
      <div className="spec-chips">
        <span>
          {result.config.countries
            .map((c) => manifest.countries.find((x) => x.iso3 === c)?.name ?? c)
            .join(" · ")}
        </span>
        {primary && (
          <span>
            {screenText(
              primary.name,
              countryIndicators(
                manifest.indicators,
                result.config.countries[0],
              ),
            )}{" "}
            · {primary.unit}
          </span>
        )}
        <span>
          {r?.actual_sample.start} → {r?.actual_sample.end}
        </span>
        {r?.irf && <span>Horizon {r.irf.periods.at(-1)}</span>}
        {(result.first_stage_largest_root ?? panel.first_stage_largest_root) !==
          undefined && (
          <span>
            First-stage largest root{" "}
            {significant(
              result.first_stage_largest_root ?? panel.first_stage_largest_root,
            )}
          </span>
        )}
        {r?.irf?.band_method && (
          <span>{parameterDisplayLabel(text(r.irf.band_method))} bands</span>
        )}
        <span>Snapshot {result.snapshot_id}</span>
      </div>
      <p className="result-label">{resultDisplayLabel(result.label)}</p>
      {!hideNumbers && numbers}
    </header>
  );
}
function reveal(selector: string) {
  const target = document.querySelector<HTMLElement>(selector);
  if (!target) return;
  let el: HTMLElement | null = target;
  while (el) {
    if (el instanceof HTMLDetailsElement) el.open = true;
    el = el.parentElement;
  }
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.querySelector<HTMLElement>("summary")?.focus();
}
export function ResultRail({
  result,
  manifest,
  showResponse,
  previouslyDisplayedChecks,
  compact = false,
}: {
  result: AnalysisResult;
  manifest: Manifest;
  showResponse: () => void;
  exportCsv: () => void;
  exportPython: () => void;
  exportLatex: () => void;
  exportPng: () => void;
  busy: boolean;
  previouslyDisplayedChecks?: Check[];
  compact?: boolean;
}) {
  const tiers = warningTiers(result.checks);
  const headlines = robustnessHeadlines(result, manifest);
  const findings = distinctFindings(result.checks);
  const firstFinding =
    tiers.blocking[0] ??
    tiers.important[0] ??
    tiers.notes[0] ??
    tiers.sourceFindings[0];
  const disclosed = resultDisclosureChecks(
    result.checks,
    previouslyDisplayedChecks,
  );
  const templateRows = records(result.template_sensitivity);
  const variants = templateRows.length
    ? templateRows
    : result.results.flatMap((r) => r.sensitivity.variants);
  const unique = [
    ...new Map(variants.map((v) => [text(v.id ?? v.variant_id), v])).values(),
  ];
  const jump = (selector: string) => {
    showResponse();
    requestAnimationFrame(() => reveal(selector));
  };
  return (
    <aside className="result-rail stack">
      <section className="card stack">
        <p className="overline">Specification sensitivity</p>
        <h2>How robust is it?</h2>
        <p className="small muted">
          Existing comparisons, with their original estimands and
          material-change flags.
        </p>
        {headlines.map((headline, i) => (
          <div key={i} className="robustness-headline">
            <p>
              <strong>{headline.line}</strong>
            </p>
            <p className="small muted">{headline.scope}</p>
          </div>
        ))}
        <details className="robustness-comparisons" open={!compact}>
          <summary>Specification comparisons</summary>
          <div className="robust-row">
            <strong>Current specification</strong>
            <span className="badge">Default</span>
          </div>
          {unique.map((v, i) => {
            const comparisons = records(v.comparison);
            const material = comparisons.some((c) => c.material === true);
            const affected = [
              ...new Set(
                comparisons
                  .filter((c) => c.material === true)
                  .map((c) => text(c.outcome ?? c.term, "")),
              ),
            ].filter(Boolean);
            const different =
              v.same_estimand === false ||
              v.include_in_agreement_counts === false;
            const label = material
              ? "Changes the answer"
              : different
                ? "Different estimand"
                : comparisons.length
                  ? "Holds"
                  : v.variant_id === "baseline"
                    ? "Default"
                    : v.status === "ok"
                      ? "Reported"
                      : text(v.status, "Reported");
            return (
              <button
                className="robust-row"
                key={i}
                onClick={() =>
                  jump(
                    '[data-testid="v2-template-sensitivity"], .sensitivity-section, [data-testid="forecast-results"]',
                  )
                }
              >
                <span>
                  {sensitivityDisplayLabel(v)}
                  {affected.length > 0 && (
                    <small>
                      {affected
                        .map((id) =>
                          termLabel(
                            id,
                            countryIndicators(
                              manifest.indicators,
                              result.config.countries[0],
                            ),
                          ),
                        )
                        .join(" · ")}
                    </small>
                  )}
                  {different && (
                    <small>Excluded from same-estimand agreement</small>
                  )}
                </span>
                <span className={material ? "material-badge" : "small muted"}>
                  {label}
                </span>
              </button>
            );
          })}
          {!unique.length && (
            <p className="small">
              {result.sensitivity_pending
                ? "Sensitivity is computing in the background."
                : "See the method-specific comparisons below."}
            </p>
          )}
          <button
            className="link"
            onClick={() =>
              jump(
                '[data-testid="v2-template-sensitivity"], .sensitivity-section, [data-testid="forecast-results"]',
              )
            }
          >
            All sensitivity details ↗
          </button>
          <p className="small muted">
            “Changes the answer” is descriptive, not a significance test.
            Alternative methods or estimands are never combined into one
            agreement count.
          </p>
        </details>
      </section>
      {!compact && (
        <section className="card stack">
          <p className="overline">Read before citing</p>
          <h2>{findings.length} findings in total</h2>
          <p className="small muted">
            {tiers.importantCount} important findings · complete list below
          </p>
          {(firstFinding ? [firstFinding] : []).map((c, i) => (
            <p className="compact-finding" key={i}>
              {c.instances.some((instance) => disclosed.has(instance)) && (
                <span className="warning-phase">Found after estimation</span>
              )}
              {readableCheckMessage(c, manifest.indicators)}
            </p>
          ))}
          {!findings.length && (
            <p className="small muted">
              No important findings for this specification. Source notes and
              technical details remain below.
            </p>
          )}
          <button className="link" onClick={() => jump("#all-findings")}>
            All findings, source notes & technical details ↗
          </button>
        </section>
      )}
    </aside>
  );
}
export function ResultTableView({
  result,
  manifest,
  tab,
}: {
  result: AnalysisResult;
  manifest: Manifest;
  tab: string;
}) {
  if (tab === "response") return null;
  return (
    <section className="card stack" data-testid="result-table-view">
      <h2>{tab === "coefficients" ? "Coefficients" : "Samples & data"}</h2>
      {result.results.map((r, index) => (
        <section className="stack" key={index}>
          <h3>
            {manifest.countries.find((c) => c.iso3 === r.country)?.name ??
              r.country}{" "}
            {text(r.outcome, "")}
          </h3>
          {tab === "coefficients" ? (
            r.coefficients_table?.length ? (
              <DataTable
                rows={r.coefficients_table.map((c) => ({
                  ...c,
                  term: termLabel(c.term, manifest.indicators),
                }))}
                columns={["term", "estimate", "std_error", "lower", "upper"]}
              />
            ) : (
              <p>
                This output has no coefficient table. Use Response / Estimates
                for its reported curves or metrics.
              </p>
            )
          ) : (
            <>
              <DataTable
                rows={[
                  {
                    Start: r.actual_sample.start,
                    End: r.actual_sample.end,
                    Observations: r.actual_sample.nobs,
                    "Common observations": r.actual_sample.common_nobs,
                    "Dropped periods": r.actual_sample.dropped_periods.length,
                  },
                ]}
              />
              {Object.keys(record(record(r.panel).country_samples)).length >
                0 && (
                <DataTable
                  rows={Object.entries(
                    record(record(r.panel).country_samples),
                  ).map(([iso, sample]) => ({
                    Country:
                      manifest.countries.find((c) => c.iso3 === iso)?.name ??
                      iso,
                    ...record(sample),
                  }))}
                />
              )}
              <details>
                <summary>Every dropped period and conversion</summary>
                <DataTable rows={r.actual_sample.dropped_periods} />
                <pre>
                  {JSON.stringify(
                    {
                      conversions: r.actual_sample.frequency_conversion,
                      transforms: r.actual_sample.transforms,
                      country_samples: record(r.panel).country_samples,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </>
          )}
        </section>
      ))}
    </section>
  );
}

export function ResultExports({
  result,
  busy,
  exportCsv,
  exportPython,
  exportLatex,
  exportPng,
}: {
  result: AnalysisResult;
  busy: boolean;
  exportCsv: () => void;
  exportPython: () => void;
  exportLatex: () => void;
  exportPng: () => void;
}) {
  return (
    <section className="card stack">
      <p className="overline">Take it with you</p>
      <h2>Export this result</h2>
      <div className="export-grid">
        <button
          data-testid="export-png"
          disabled={busy || result.status !== "ok"}
          onClick={exportPng}
        >
          PNG
        </button>
        <button data-testid="export-csv" disabled={busy} onClick={exportCsv}>
          CSV
        </button>
        <button disabled={busy} onClick={exportLatex}>
          LaTeX table
        </button>
        <button
          disabled={busy || result.status !== "ok"}
          onClick={exportPython}
          data-testid="export-python"
        >
          Python
        </button>
      </div>
      <p className="small muted">
        The snapshot, sample and full precision travel with the export.
      </p>
    </section>
  );
}
