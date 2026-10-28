import { ResultDataTable as DataTable } from "./ResultDataTable";
import { keyFacts } from "../resultFacts";
import { relationshipEligible } from "../additionalViewData";
import { baselineResultChecks } from "../resultPresentation";
import {
  PrimaryChartProvider,
  PrimaryChartSlot,
  CoefficientChartSlot,
} from "./PrimaryChart";
import { ResultSpecification } from "./ResultSpecification";
import { chartDisplay, resultDisplayLabel, screenText } from "../chartDisplay";
import { sensitivityDisplayLabel } from "../sensitivityLabels";
import {
  ResultOverview,
  ResultRail,
  ResultTableView,
  ResultExports,
} from "./ResultOverview";
import { latexTables } from "../latexExport";
import { ForecastResults } from "./ForecastResults";
import { V2TemplateResults } from "./V2TemplateResults";
import { v2Template } from "../templatesV2";
import { DiagnosticResults } from "./DiagnosticResults";
import { breakConfig, diagnosticModel } from "../diagnosticModels";
import { forecastModel } from "../forecast";
import { BvarResults } from "./BvarResults";
import {
  Fragment,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
} from "react";
import { ChartExportContext } from "../chartExportContext";
import type {
  AnalysisConfig,
  AnalysisResult,
  Check,
  CountryResult,
  CountryBundle,
  Manifest,
  JsonRecord,
} from "../types";
import {
  csv,
  download,
  number,
  significant,
  tableValue,
  record,
  records,
  strings,
  text,
} from "../format";
import { Checks, Field } from "./Common";
import { Chart } from "./Chart";
import {
  chartData,
  termLabel,
  coefficientInterval,
  panelSourceNames,
  resultTableBlocks,
  analysisCsvRows,
  readingBullets,
  selectedPeakFootnote,
  sensitivityRows,
  shockHeading,
  specificationLabel,
} from "../resultData";
import "../results.css";
import { exportPng } from "../pngExport";
import { TemplateSources } from "./TemplateSources";
import { countryIndicators } from "../displayLabels";
import { getTemplateSources, type AnalysisRuntime } from "../runtime";
import { CountryComparison } from "./CountryComparison";
import { PanelResults, PanelCovarianceTable } from "./PanelResults";
import { MethodComparison } from "./MethodComparison";
const RelationshipViews = lazy(() =>
  import("./AdditionalViews").then((m) => ({ default: m.RelationshipViews })),
);
const TechnicalExtensions = lazy(() =>
  import("./TechnicalExtensions").then((m) => ({
    default: m.TechnicalExtensions,
  })),
);

function TemplateCorrectionSummary({
  result,
  manifest,
}: {
  result: AnalysisResult;
  manifest: Manifest;
}) {
  const template = result.config.model.params.template_id;
  if (template === "tur_pass_through") {
    const pass = record(result.results[0]?.pass_through);
    if (pass.status !== "ok") return <p>{text(pass.reason)}</p>;
    return (
      <section className="card stack" data-testid="pass-through-headline">
        <h2>Cumulative pass-through ratio</h2>
        <p>
          {text(pass.definition)}. {text(pass.sign_convention)}
        </p>
        <DataTable
          countries={manifest.countries}
          rows={records(pass.horizons)
            .filter((r) => [6, 12, 24].includes(Number(r.horizon)))
            .map((r) => ({
              Months: r.horizon,
              Ratio: significant(r.ratio),
              "68% interval": `${significant(record(record(r.bands)["0.68"]).lower)} to ${significant(record(record(r.bands)["0.68"]).upper)}`,
              "Cumulative FX (%)": significant(r.fx_cumulative),
            }))}
        />
        <p>
          {text(pass.interval_method)}. {text(pass.denominator_note)}
        </p>
        {records(pass.horizons).some((r) => r.denominator_weak) && (
          <p role="alert">
            Important: at least one exchange-rate denominator is weak; its ratio
            interval may be unreliable.
          </p>
        )}
        <p>Secondary CPI display: {text(pass.secondary_label)}.</p>
      </section>
    );
  }
  if (template !== "same_ecb_shock") return null;
  const rows = records(result.template_sensitivity);
  const names = [
    "rate_3m",
    "bis",
    "end_2019",
    "exclude_2014_2022",
    "common_window",
    "lags_4",
    "hac",
    "year_on_year_inflation",
    "national_var",
  ];
  return (
    <section className="card stack" data-testid="ecb-progressive-summary">
      <p>{text(result.magnitude_note)}</p>
      {Number(result.first_stage_largest_root) >= 0.98 && (
        <p role="alert" className="warning-box">
          Warning: the first-stage VAR is{" "}
          {Number(result.first_stage_largest_root) >= 1
            ? "unstable"
            : "near a unit root"}{" "}
          (largest companion root {number(result.first_stage_largest_root, 4)}).
          Its orthogonalised residuals remain usable; persistence and
          identification warrant caution.
        </p>
      )}
      <section>
        <h3>Peak responses: one standard deviation and +25 bp</h3>
        <DataTable
          countries={manifest.countries}
          rows={records(result.scaled_peaks).map((r) => ({
            Country: r.country,
            Response:
              r.response === "cpi"
                ? "HICP"
                : r.response === "gdp_real"
                  ? "GDP"
                  : "Unemployment",
            Quarter: r.horizon,
            "One SD": significant(r.one_sd),
            "+25 bp": significant(r.plus_25bp),
          }))}
        />
        <p>
          GDP/HICP: cumulative % change in the level; unemployment: percentage
          points. Linear rescaling of the same response.
        </p>
      </section>
      {result.config.comparison?.enabled !== false && (
        <details className="secondary-section ">
          <summary>Specification sensitivity</summary>
          <div aria-live="polite" data-testid="sensitivity-progress">
            <strong>
              {result.sensitivity_pending
                ? "Baseline ready · sensitivity computing in the background"
                : "Sensitivity complete"}
            </strong>
            <ul>
              {names.map((name) => {
                const row = rows.find((r) => r.variant_id === name);
                return (
                  <li key={name}>
                    {
                      (
                        {
                          rate_3m: "EA 3-month rate",
                          bis: "BIS policy rate",
                          end_2019: "End sample in 2019",
                          exclude_2014_2022: "Exclude 2014–2022",
                          common_window: "Common window",
                          lags_4: "Four lags",
                          hac: "HAC inference",
                          year_on_year_inflation: "Year-on-year inflation",
                          national_var: "National VAR",
                        } as Record<string, string>
                      )[name]
                    }
                    :{" "}
                    {row
                      ? row.status === "ok"
                        ? "Ready"
                        : text(row.status)
                      : result.sensitivity_pending
                        ? "Pending"
                        : "Not run"}
                    {row && Number(row.first_stage_largest_root) >= 0.98 && (
                      <span>
                        {" "}
                        · Warning:{" "}
                        {Number(row.first_stage_largest_root) >= 1
                          ? "unstable"
                          : "near-unit-root"}{" "}
                        first stage, root{" "}
                        {number(row.first_stage_largest_root, 4)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
            <p>Joint bootstrap is on demand.</p>
          </div>
        </details>
      )}
    </section>
  );
}

interface Props {
  runtime?: AnalysisRuntime;
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
  hideCharts = false,
  hideChecks = false,
  analysisConfig,
  onSourceCard,
  previouslyDisplayedChecks,
  insightCoefficient = false,
}: {
  result: CountryResult;
  manifest: Manifest;
  comparison: boolean;
  first: boolean;
  cards: CountryBundle["cards"];
  compact?: boolean;
  hideCharts?: boolean;
  hideChecks?: boolean;
  insightCoefficient?: boolean;
  analysisConfig?: AnalysisConfig;
  onSourceCard?: (country: string, conceptId: string) => void;
  previouslyDisplayedChecks?: Check[];
}) {
  const exportContext = useContext(ChartExportContext);
  const indicators = countryIndicators(
    manifest.indicators.map((indicator) => ({
      ...indicator,
      ...cards.find((card) => card.concept_id === indicator.concept_id),
    })),
    result.country,
  );
  const charts = chartData(result, indicators);
  const blocks = resultTableBlocks(result);
  const shortDescriptiveTables = blocks.filter(
    (block) =>
      (["test.adf_kpss_pp", "test.granger"].includes(result.model_id) &&
        block.title === "Tests, null hypotheses and effective samples") ||
      ((result.model_id.startsWith("desc.") ||
        result.model_id === "sing.rolling") &&
        [
          "Country comparison and rankings",
          "Full-sample correlations",
          "Tests, null hypotheses and effective samples",
          "Last-window coefficients and intervals",
        ].includes(block.title) &&
        block.rows.length <= 12 &&
        (block.columns?.length ?? Object.keys(block.rows[0] ?? {}).length) <=
          8),
  );
  const inlineCoefficients =
    !hideCharts && charts.some((chart) => chart.coefficient)
      ? blocks.find(
          (block) =>
            block.title.includes("coefficients") ||
            block.title === "Coefficients and intervals",
        )
      : undefined;
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
  const comparisonDisplayLabel = sensitivityDisplayLabel(variant ?? {});
  const comparisonCurveVisible =
    !result.pass_through || Boolean(charts.some((chart) => chart.variable));
  const sensitivity = result.sensitivity;
  const lagCriteria = record(record(sensitivity).lag_criteria);
  const selectedLags = record(lagCriteria.selected_lags);
  const rows = sensitivityRows(result, indicators).map((row): JsonRecord => ({
    ...row,
    ...(typeof row.Term === "string"
      ? { Term: screenText(row.Term, indicators) }
      : {}),
  }));
  const sample = result.actual_sample;
  const name =
    manifest.countries.find((c) => c.iso3 === result.country)?.name ??
    result.country;
  const [exportError, setExportError] = useState("");
  useEffect(() => {
    const handler = (event: Event) => {
      if (
        !first ||
        !charts.length ||
        result.status !== "ok" ||
        forecastModel(result.model_id) ||
        diagnosticModel(result.model_id)
      )
        return;
      const panel =
        (event as CustomEvent<{ mode?: string }>).detail?.mode === "panel";
      const selected = panel ? charts : [selectedChart];
      const rendered = selected.map((chart) => {
        const index = charts.indexOf(chart);
        const response = records(record(variant?.metrics).responses).find(
          (item) => item.variable === charts[index]?.variable,
        );
        return {
          ...chart,
          pngNote:
            result.pass_through && chart.variable === "cpi"
              ? text(record(result.pass_through).secondary_label)
              : undefined,
          pngComparisonLabel:
            result.pass_through && chart.variable === "cpi"
              ? comparisonLabel
              : undefined,
          points: chart.points.map((point) => {
            if (!result.irf) return point;
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
          }),
        };
      });
      const template = manifest.templates.find(
        (t) =>
          analysisConfig &&
          t.config.model.id === analysisConfig.model.id &&
          t.config.series.map((s) => s.concept_id).join() ===
            analysisConfig.series.map((s) => s.concept_id).join(),
      );
      const modelTitle =
        manifest.models.find((m) => m.id === result.model_id)?.title ??
        "MacroLab analysis";
      const sources = analysisConfig?.model.id.startsWith("panel.")
        ? (exportContext?.sources ?? [])
        : [
            ...new Set(
              cards
                .filter(
                  (c) =>
                    !analysisConfig ||
                    (analysisConfig.series.some(
                      (s) => s.concept_id === c.concept_id,
                    ) &&
                      !(
                        analysisConfig.model.params.template_id ===
                          "same_ecb_shock" && c.concept_id === "policy_rate"
                      )),
                )
                .flatMap((c) =>
                  records(c.source_segments).map((s) => text(s.source)),
                ),
            ),
          ]
            .filter(Boolean)
            .sort();
      setExportError("");
      const stageSources =
        analysisConfig?.model.params.template_id === "same_ecb_shock"
          ? getTemplateSources(
              String(analysisConfig.model.params.policy_measure),
            )
          : Promise.resolve([]);
      void stageSources
        .then((extra) =>
          exportPng(rendered, {
            snapshot: analysisConfig?.snapshot_id,
            analysis: result.pass_through
              ? "Exchange-rate pass-through"
              : (template?.title ?? modelTitle),
            scenario:
              result.irf && analysisConfig
                ? shockHeading(result.irf, analysisConfig, indicators)
                : undefined,
            country: name,
            sample: `Actual sample: ${sample.start}–${sample.end} · n = ${sample.nobs}`,
            frequency: analysisConfig?.frequency ?? "Q",
            horizon: Boolean(result.irf),
            forecast: forecastModel(result.model_id),
            sources: [
              ...new Set([
                ...sources,
                ...extra.map((card) => text(card.source)),
              ]),
            ],
            bandLevel:
              result.irf?.band_level ??
              analysisConfig?.outputs.confidence ??
              0.95,
            comparisonLabel: result.pass_through
              ? `${comparisonLabel} · secondary CPI only`
              : result.irf
                ? comparisonLabel
                : "Fitted / trend",
            note: result.pass_through
              ? undefined
              : result.irf
                ? selectedPeakFootnote
                : undefined,
          }),
        )
        .catch((error) => setExportError(String(error)));
    };
    window.addEventListener("macrolab-export-png", handler);
    return () => window.removeEventListener("macrolab-export-png", handler);
  }, [
    analysisConfig,
    cards,
    charts,
    comparison,
    comparisonLabel,
    exportContext?.sources,
    first,
    indicators,
    manifest,
    name,
    result,
    sample,
    selectedChart,
    variant,
  ]);
  const responseControls = (
    <>
      {comparison && comparisonCurveVisible && alternatives.length > 0 && (
        <Field
          label={
            result.pass_through
              ? "Compare secondary CPI response with"
              : "Compare response curves with"
          }
        >
          <select
            value={text(variant?.variant_id)}
            onChange={(event) => setVariantId(event.target.value)}
          >
            {alternatives.map((item) => (
              <option key={text(item.variant_id)} value={text(item.variant_id)}>
                {sensitivityDisplayLabel(item)}
              </option>
            ))}
          </select>
        </Field>
      )}
      <div className="legend">
        <span>
          <i
            className={charts[0]?.coefficient ? "legend-dot" : "legend-line"}
          />
          {charts[0]
            ? chartDisplay(result, charts[0], indicators).estimateLabel
            : "Reported value"}
        </span>
        {charts.some((chart) =>
          chart.points.some((point) => point.lower !== undefined),
        ) && (
          <span>
            <i className={result.irf ? "legend-band" : "legend-whisker"} />
            {result.irf
              ? `${Math.round(result.irf.band_level * 100)}% pointwise interval`
              : coefficientInterval(result)}
          </span>
        )}
        {comparison && comparisonCurveVisible && variant && (
          <span>
            <i className="legend-line comparison" />
            {comparisonDisplayLabel} · point estimate
          </span>
        )}
      </div>
      {Boolean(result.pass_through) && comparison && (
        <p className="small muted">
          Specification comparisons below refer to the secondary CPI response.
        </p>
      )}
    </>
  );
  return (
    <section className="stack result-country">
      {exportError && <p role="alert">PNG export failed: {exportError}</p>}
      <div className="row between country-result-heading">
        <h2>{name}</h2>
        <span className="mono">
          {sample.start ?? "No estimate"} → {sample.end ?? "—"} · n ={" "}
          {sample.nobs}
        </span>
      </div>
      {!hideChecks && (
        <Checks
          showEstimationPhase
          previouslyDisplayedChecks={previouslyDisplayedChecks}
          checks={result.checks}
          onSourceCard={onSourceCard}
          indicators={indicators}
          countries={manifest.countries}
        />
      )}
      {result.status === "ok" && (
        <>
          {!hideCharts && (
            <>
              {charts.length > 1 && (
                <Field label={"Chart for selected PNG export"}>
                  <select
                    data-testid="export-chart-selector"
                    value={selectedChart?.name}
                    onChange={(event) => setChartName(event.target.value)}
                  >
                    {charts.map((chart) => (
                      <option key={chart.name} value={chart.name}>
                        {screenText(chart.name, indicators)}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              <div
                className={`charts-grid ${result.pass_through ? "pass-through-charts" : ""}`}
              >
                {charts.map((chart) => {
                  const index = charts.indexOf(chart);
                  return (
                    <Fragment key={chart.name}>
                      <Chart
                        {...chart}
                        primary={first && index === 0 ? 3 : 0}
                        controls={
                          index ===
                          (result.pass_through
                            ? Math.max(
                                0,
                                charts.findIndex((c) => c.variable === "cpi"),
                              )
                            : 0)
                            ? responseControls
                            : undefined
                        }
                        insight={
                          insightCoefficient && Boolean(chart.coefficient)
                        }
                        title={chart.name}
                        {...chartDisplay(result, chart, indicators)}
                        comparisonShortLabel={
                          result.irf && variant
                            ? variant?.variant_id === "reverse_order"
                              ? "Reversed order"
                              : variant?.variant_id === "sample_2003"
                                ? "Since 2003"
                                : comparisonDisplayLabel
                            : chartDisplay(result, chart, indicators)
                                .comparisonShortLabel
                        }
                        pngNote={
                          result.pass_through && chart.variable === "cpi"
                            ? text(record(result.pass_through).secondary_label)
                            : undefined
                        }
                        exportContext={
                          exportContext && {
                            ...exportContext,
                            country: name,
                            sample: `Actual sample: ${sample.start}–${sample.end} · n = ${sample.nobs} · Snapshot ${analysisConfig?.snapshot_id}`,
                            horizon: Boolean(result.irf),
                            forecast: forecastModel(result.model_id),
                          }
                        }
                        comparisonDisplayLabel={
                          result.irf ? comparisonDisplayLabel : "Fitted / trend"
                        }
                        comparisonLabel={
                          result.irf ? comparisonLabel : "Fitted / trend"
                        }
                        points={chart.points.map((point) => {
                          if (!result.irf) return point;
                          const response = records(
                            record(variant?.metrics).responses,
                          ).find(
                            (item) => item.variable === charts[index]?.variable,
                          );
                          const position =
                            (
                              response?.periods as number[] | undefined
                            )?.indexOf(Number(point.period)) ?? -1;
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
                      {chart.coefficient && inlineCoefficients && (
                        <section
                          className="card stack"
                          data-testid="coefficient-table"
                        >
                          <h3>{inlineCoefficients.title}</h3>
                          <DataTable
                            countries={manifest.countries}
                            rows={inlineCoefficients.rows}
                            columns={inlineCoefficients.columns}
                            renderCell={(row, column) =>
                              column === "term"
                                ? termLabel(text(row[column]), indicators)
                                : tableValue(column, row[column])
                            }
                          />
                        </section>
                      )}
                    </Fragment>
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
                <p className="small muted peak-footnote">
                  {selectedPeakFootnote}
                </p>
              )}
            </>
          )}
          {!forecastModel(result.model_id) && (
            <div className="result-grid">
              <details className="card stack sensitivity-section secondary-section">
                <summary>Specification sensitivity</summary>
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
                            <section
                              key={index}
                              className="sensitivity-mini-card"
                            >
                              <h3>
                                <strong>
                                  {text(row.Response ?? row.Term)}
                                </strong>
                                <span>
                                  {text(
                                    row["Baseline peak"] ??
                                      row["Baseline estimate"],
                                  )}
                                </span>
                              </h3>
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
                            </section>
                          ))}
                        </div>
                      ) : (
                        <DataTable countries={manifest.countries} rows={rows} />
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
                              <strong>{sensitivityDisplayLabel(v)}</strong> ·{" "}
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
                                <section>
                                  <h3>Variant estimates</h3>
                                  <DataTable
                                    countries={manifest.countries}
                                    rows={records(
                                      record(v.metrics).responses ??
                                        record(v.metrics).coefficients,
                                    )}
                                  />
                                </section>
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
                      countries={manifest.countries}
                      rows={records(lagCriteria.candidates).map(
                        (candidate) => ({
                          Lag: candidate.lag,
                          AIC: candidate.aic,
                          BIC: candidate.bic,
                          HQIC: candidate.hqic,
                        }),
                      )}
                    />
                  </details>
                )}
              </details>
              <details className="card stack reading secondary-section">
                <summary>Extended interpretation and method notes</summary>
                <h2>Reading the result</h2>
                <ul data-testid="reading-bullets">
                  {readingBullets(result, indicators).map((bullet, index) => (
                    <li key={index}>{screenText(bullet, indicators)}</li>
                  ))}
                </ul>
              </details>
            </div>
          )}
          {shortDescriptiveTables.map((block) => (
            <section
              className="card stack"
              key={block.title}
              data-testid="short-result-summary"
            >
              <h3>{block.title}</h3>
              <DataTable
                primary
                countries={manifest.countries}
                rows={block.rows}
                columns={block.columns}
              />
            </section>
          ))}
          <details className="card technical-details">
            <summary>
              Detailed diagnostics, samples, sources and provenance
            </summary>
            <h3>Tables, diagnostics and full method notes</h3>
            <div className="stack">
              {blocks
                .filter(
                  (block) =>
                    block !== inlineCoefficients &&
                    !shortDescriptiveTables.includes(block),
                )
                .map((block) => (
                  <section key={block.title}>
                    <h3>{block.title}</h3>
                    {result.model_id.startsWith("panel.") &&
                    block.title.startsWith("Covariance sensitivity: ") ? (
                      <PanelCovarianceTable
                        rows={block.rows}
                        lp={result.model_id === "panel.lp"}
                        label={block.title.replace(
                          "Covariance sensitivity: ",
                          "",
                        )}
                        indicators={indicators}
                      />
                    ) : (
                      <DataTable
                        countries={manifest.countries}
                        rows={
                          result.model_id.startsWith("panel.")
                            ? block.rows.map((r) =>
                                typeof r.term === "string"
                                  ? {
                                      ...r,
                                      term: termLabel(r.term, indicators),
                                    }
                                  : r,
                              )
                            : block.rows
                        }
                        columns={block.columns}
                      />
                    )}
                  </section>
                ))}
              {Boolean(result.fevd) && (
                <section>
                  <h3>Forecast-error variance decomposition</h3>
                  <p className="small">
                    Shares by response, horizon and identified shock. Point
                    estimates only.
                  </p>
                  <DataTable
                    countries={manifest.countries}
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
                </section>
              )}
              <section>
                <h3>Actual sample, conversions and diagnostics</h3>
                <p>
                  {sample.nobs} estimation observations from{" "}
                  {sample.common_nobs} complete common observations.{" "}
                  {sample.dropped_periods.length} requested periods dropped.
                </p>
                <DataTable
                  countries={manifest.countries}
                  rows={sample.dropped_periods}
                />
                <h3>Frequency conversions</h3>
                <DataTable
                  countries={manifest.countries}
                  rows={Object.entries(sample.frequency_conversion).map(
                    ([concept, value]) => ({ concept, ...record(value) }),
                  )}
                />
                <h3>Transformations</h3>
                <DataTable
                  countries={manifest.countries}
                  rows={Object.entries(sample.transforms).map(
                    ([concept, value]) => ({ concept, ...record(value) }),
                  )}
                />
                <h3>Diagnostics</h3>
                <DataTable
                  countries={manifest.countries}
                  rows={Object.entries(result.diagnostics ?? {})
                    .filter(([, value]) => typeof value !== "object")
                    .map(([diagnostic, value]) => ({ diagnostic, value }))}
                />
              </section>
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
  runtime,
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
  const [selectedCountry, setSelectedCountry] = useState("DEU");
  const [pngMode, setPngMode] = useState("primary");
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
  const facts = keyFacts(result, manifest);
  const baselineChecks = baselineResultChecks(result);
  const irf = result.results.find((r) => r.irf)?.irf;
  const config = result.config;
  const breakDiagnostic = breakConfig(result);
  const model = manifest.models.find((m) => m.id === config.model.id);
  const template = config.model.params.template_id;
  const ecbTemplate = template === "same_ecb_shock";
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
  const exportDisplayedPng = () => {
    if (pngMode === "primary") {
      const button = document.querySelector<HTMLButtonElement>(
        '[data-testid="primary-chart"] [data-chart-export="png"]',
      );
      if (button) {
        button.click();
        return;
      }
    }
    window.dispatchEvent(
      new CustomEvent("macrolab-export-png", {
        detail: { mode: pngMode === "primary" ? "selected" : pngMode },
      }),
    );
  };
  return (
    <PrimaryChartProvider>
      <ChartExportContext.Provider
        value={{
          snapshot: result.snapshot_id,
          analysis:
            manifest.templates.find((t) => t.id === template)?.title ??
            model?.title ??
            "MacroLab analysis",
          country: config.countries
            .map(
              (code) =>
                manifest.countries.find((c) => c.iso3 === code)?.name ?? code,
            )
            .join(" / "),
          sample: `Snapshot ${result.snapshot_id} · ${result.results.map((r) => `${r.country}: ${r.actual_sample.start}–${r.actual_sample.end}, n=${r.actual_sample.nobs}`).join("; ")}`,
          sources: config.model.id.startsWith("panel.")
            ? panelSourceNames(config, bundles)
            : [
                ...new Set([
                  ...Object.values(bundles).flatMap((b) =>
                    b.cards
                      .filter((c) =>
                        config.series.some(
                          (s) => s.concept_id === c.concept_id,
                        ),
                      )
                      .flatMap((c) =>
                        records(c.source_segments).map((s) => text(s.source)),
                      ),
                  ),
                  ...(config.model.id === "test.break" &&
                  config.model.params.source_variant &&
                  config.model.params.source_variant !== "none"
                    ? ["ECB"] // All accepted first-stage variants use ECB SA HICP.
                    : []),
                ]),
              ],
          frequency: config.frequency,
          horizon: Boolean(irf),
          forecast: forecastModel(result.config.model.id),
          bandLevel: irf?.band_level ?? config.outputs.confidence ?? 0.95,
          comparisonLabel: "Comparison",
        }}
      >
        <Fragment key={result.config_hash}>
          <section
            data-testid="screen-results"
            className="stack results-screen visual-results research-results"
            data-result-family={config.model.id}
          >
            <div className="result-title-row">
              <ResultOverview
                result={result}
                manifest={manifest}
                edit={edit}
                hideNumbers
              />
              <div className="row result-primary-actions">
                <button className="link" onClick={edit}>
                  Edit assumptions
                </button>
                <button
                  data-testid="share-link"
                  disabled={busy}
                  onClick={share}
                >
                  Share link
                </button>
                <details
                  className="result-export-menu"
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      event.currentTarget.open = false;
                      event.currentTarget.querySelector("summary")?.focus();
                    }
                  }}
                >
                  <summary>Export results</summary>
                  <div className="result-export-popover">
                    <label className="field">
                      <span>PNG scope</span>
                      <select
                        aria-label="PNG scope"
                        value={pngMode}
                        onChange={(e) => setPngMode(e.target.value)}
                      >
                        <option value="primary">Main chart</option>
                        <option value="selected">Selected chart below</option>
                        <option value="panel">All response charts</option>
                      </select>
                    </label>
                    <ResultExports
                      result={result}
                      busy={busy || Boolean(result.sensitivity_pending)}
                      exportCsv={exportCsv}
                      exportPython={exportPython}
                      exportLatex={() =>
                        download(
                          latexTables(result, manifest),
                          "macrolab-results.tex",
                          "application/x-tex",
                        )
                      }
                      exportPng={exportDisplayedPng}
                    />
                    <p className="small muted">
                      Each figure also has its own PNG download. The model-chart
                      selector remains beside the corresponding result table or
                      chart.
                    </p>
                  </div>
                </details>
              </div>
            </div>
            {result.status !== "ok" && (
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
                · {resultDisplayLabel(result.label)}
              </div>
            )}
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
            {facts.length > 0 && (
              <section className="card key-facts" data-testid="key-facts">
                <h2>Key facts</h2>
                {facts.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </section>
            )}
            <ResultSpecification result={result} manifest={manifest} />
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
            <section
              className="result-hero-workspace"
              aria-label="Main result and interpretation"
            >
              <PrimaryChartSlot />
              <aside
                className="result-insight-stack"
                aria-label="Estimate and robustness summary"
              >
                <ResultOverview
                  result={result}
                  manifest={manifest}
                  edit={edit}
                  numbersOnly
                  conciseNumbers={facts.length > 0}
                />
                <CoefficientChartSlot />
                <ResultRail
                  compact
                  result={result}
                  manifest={manifest}
                  previouslyDisplayedChecks={previouslyDisplayedChecks}
                  showResponse={() => {}}
                  busy={busy}
                  exportCsv={exportCsv}
                  exportPython={exportPython}
                  exportLatex={() => {}}
                  exportPng={() => {}}
                />
              </aside>
            </section>
            <section
              id="all-findings"
              className="baseline-findings"
              data-testid="baseline-findings"
            >
              <h2>Model checks and data notes</h2>
              <Checks
                compact
                checks={baselineChecks}
                showEstimationPhase
                previouslyDisplayedChecks={previouslyDisplayedChecks}
                onSourceCard={onSourceCard}
                indicators={
                  config.countries.length === 1
                    ? countryIndicators(
                        manifest.indicators,
                        config.countries[0],
                      )
                    : manifest.indicators
                }
                countries={manifest.countries}
              />
            </section>

            <section
              className="result-details stack"
              data-testid="result-details"
            >
              <div className="result-detail-workspace">
                <div className="result-main">
                  <div className="result-response-content stack">
                    {runtime && (
                      <Suspense fallback={<p>Loading relationship view…</p>}>
                        <RelationshipViews
                          result={result}
                          manifest={manifest}
                          runtime={runtime}
                        />
                      </Suspense>
                    )}
                    <V2TemplateResults result={result} manifest={manifest} />
                    {!v2Template(template) &&
                      result.results
                        .filter(
                          (r) =>
                            r.model_id.startsWith("panel.") ||
                            r.model_id === "bvar.minn" ||
                            diagnosticModel(r.model_id) ||
                            forecastModel(r.model_id),
                        )
                        .map((r) => (
                          <div key={`${r.country}-${text(r.outcome)}`}>
                            <PanelResults result={r} manifest={manifest} />
                            <DiagnosticResults
                              result={r}
                              manifest={manifest}
                              first={r === result.results[0]}
                            />
                            <BvarResults result={r} manifest={manifest} />
                            <ForecastResults
                              result={r}
                              manifest={manifest}
                              first={r === result.results[0]}
                            />
                          </div>
                        ))}
                    {ecbTemplate && (
                      <CountryComparison
                        result={result}
                        manifest={manifest}
                        bundles={bundles}
                        compact={false}
                        country={
                          result.results.some(
                            (r) => r.country === selectedCountry,
                          )
                            ? selectedCountry
                            : result.results[0].country
                        }
                        selectCountry={setSelectedCountry}
                      />
                    )}
                    <div
                      className={`country-output-grid ${result.results.length > 1 ? "multiple-country-outputs" : ""}`}
                    >
                      {result.results.map((r, index) => (
                        <section
                          key={`${r.country}-${text(r.outcome)}`}
                          className={
                            ecbTemplate
                              ? "card country-details"
                              : "result-wrapper"
                          }
                        >
                          <ResultsCountry
                            key={r.country}
                            result={r}
                            analysisConfig={config}
                            manifest={manifest}
                            comparison={comparison}
                            hideChecks
                            insightCoefficient={
                              Boolean(runtime) &&
                              result.results.length === 1 &&
                              r.model_id === "sing.ols" &&
                              relationshipEligible(config, r)
                            }
                            first={
                              !ecbTemplate &&
                              !v2Template(template) &&
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
                            compact={false}
                            hideCharts={
                              ecbTemplate ||
                              r.model_id === "bvar.minn" ||
                              diagnosticModel(r.model_id) ||
                              forecastModel(r.model_id)
                            }
                            onSourceCard={onSourceCard}
                            previouslyDisplayedChecks={
                              previouslyDisplayedChecks
                            }
                          />
                        </section>
                      ))}
                    </div>
                    {runtime &&
                      !ecbTemplate &&
                      ["var.ols", "ident.recursive", "lp.ols"].includes(
                        config.model.id,
                      ) &&
                      result.results
                        .filter((r) => r.status === "ok" && r.irf)
                        .map((r) => (
                          <MethodComparison
                            key={`${result.config_hash}-${r.country}`}
                            config={config}
                            result={r}
                            manifest={manifest}
                            runtime={runtime}
                            compact={compact}
                            cards={bundles[r.country]?.cards ?? []}
                            busy={busy}
                          />
                        ))}
                    {config.model.id === "test.break" &&
                      Boolean(config.model.params.source_variant) &&
                      config.model.params.source_variant !== "none" && (
                        <TemplateSources config={config} />
                      )}
                    {Boolean(template) && !v2Template(template) && (
                      <section
                        className="card stack"
                        data-testid="v1-band-disclosure"
                      >
                        {ecbTemplate && <TemplateSources config={config} />}
                        <strong>
                          Displayed band:{" "}
                          {ecbTemplate &&
                          config.model.params.displayed_band === "joint"
                            ? "joint bootstrap (both stages)"
                            : `conditional (${config.model.params.lag_augmented ? "lag-augmented HC1" : "HAC"})`}{" "}
                          · 68% pointwise
                        </strong>
                        <p>
                          {ecbTemplate
                            ? config.model.params.displayed_band === "joint"
                              ? "Both stages are re-estimated on the common window. These bands rely on the auxiliary model and are not simultaneous across horizons."
                              : "Conditional bands understate uncertainty: they ignore estimation of the first-stage EA shock."
                            : "This is a conditional association, not an identified exchange-rate shock."}
                        </p>
                        <p>
                          Prices and output: cumulative % change in the level by
                          default. Unemployment: percentage-point change. Actual
                          windows and transformations are recorded below.
                        </p>
                        {ecbTemplate &&
                          config.model.params.displayed_band !== "joint" && (
                            <button
                              className="primary"
                              data-testid="compute-joint"
                              disabled={busy}
                              onClick={() => {
                                const next = structuredClone(config);
                                next.model.params.displayed_band = "joint";
                                next.model.params.country_window = "common";
                                rerun(next);
                              }}
                            >
                              Compute full uncertainty (joint bootstrap)
                            </button>
                          )}
                      </section>
                    )}
                    <TemplateCorrectionSummary
                      result={result}
                      manifest={manifest}
                    />
                    <section
                      className="result-tools stack"
                      aria-label="Analysis tools and disclosures"
                    >
                      {breakDiagnostic && (
                        <button
                          disabled={busy}
                          onClick={() => rerun(breakDiagnostic)}
                        >
                          Run break diagnostics for{" "}
                          {ecbTemplate || template === "same_ecb_shock_pooled"
                            ? "the ECB first-stage policy-rate equation"
                            : "this equation"}
                        </button>
                      )}
                      {runtime && (
                        <Suspense fallback={<p>Loading technical view…</p>}>
                          <TechnicalExtensions
                            key={result.config_hash}
                            config={config}
                            runtime={runtime}
                            busy={busy}
                            manifest={manifest}
                          />
                        </Suspense>
                      )}
                    </section>
                    {result.status === "ok" && (
                      <div
                        role="status"
                        data-testid="result-status"
                        data-config-hash={result.config_hash}
                        data-snapshot-id={result.snapshot_id}
                        data-model-id={config.model.id}
                        data-result-status={result.status}
                        className={
                          result.status === "ok" ? "info-box" : "error-box"
                        }
                      >
                        <strong>
                          {result.status === "ok"
                            ? "Analysis complete"
                            : "Analysis blocked or partly unavailable"}
                        </strong>{" "}
                        · {resultDisplayLabel(result.label)}
                      </div>
                    )}
                    <section className="result-heading legacy-result-heading">
                      <details className="result-reproducibility">
                        <summary>Runtime and reproducibility</summary>
                        <div>
                          <span className="overline">
                            Results · {model?.title}
                          </span>
                          <p className="runtime-result-name">
                            {v2Template(template)
                              ? manifest.templates.find(
                                  (t) => t.id === template,
                                )?.title
                              : ecbTemplate
                                ? `ECB ${config.model.params.policy_measure === "dfr" ? "DFR" : config.model.params.policy_measure === "bis" ? "BIS policy-rate" : "3-month rate"} shock: +${number(record(record(records(record(result.first_stage).results)[0]).identified_shock).requested_physical_size, 2)} pp`
                                : template === "tur_pass_through"
                                  ? "Türkiye: cumulative pass-through ratio"
                                  : irf
                                    ? shockHeading(
                                        irf,
                                        config,
                                        manifest.indicators,
                                      )
                                    : `${model?.title ?? config.model.id}: the estimated relationship`}
                          </p>
                          <p className="muted">
                            {config.countries
                              .map(
                                (c) =>
                                  manifest.countries.find((x) => x.iso3 === c)
                                    ?.name ?? c,
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
                            {ecbTemplate && (
                              <span data-testid="first-stage-root">
                                First-stage largest companion root:{" "}
                                {number(result.first_stage_largest_root, 4)}
                              </span>
                            )}
                            <span>Snapshot {result.snapshot_id}</span>
                            <span>Code {result.code_version}</span>
                            <span>{number(result.runtime_ms, 0)} ms</span>
                            <span title={result.config_hash}>
                              Config {result.config_hash.slice(0, 12)}
                            </span>
                          </div>
                        </div>
                      </details>
                      {irf && !template && (
                        <section className="card result-controls">
                          <h3>Shock size and interval precision</h3>
                          <div className="stack">
                            <Field
                              label={
                                policyShock ? "Policy shock" : "Shock size"
                              }
                            >
                              <select
                                disabled={busy}
                                value={
                                  config.outputs.irf?.shock_mode === "one_sd"
                                    ? "sd"
                                    : String(config.outputs.irf?.shock_size)
                                }
                                onChange={(e) =>
                                  shock(
                                    e.target.value === "sd"
                                      ? "one_sd"
                                      : "fixed",
                                    e.target.value === "sd"
                                      ? 1
                                      : Number(e.target.value),
                                  )
                                }
                              >
                                <option value="sd">
                                  One identified standard deviation
                                </option>
                                <option value="0.25">
                                  {policyShock
                                    ? "+25 bp"
                                    : "+0.25 transformed units"}
                                </option>
                                <option value="1">
                                  {policyShock
                                    ? "+1 pp"
                                    : "+1 transformed unit"}
                                </option>
                                {!["sd", "0.25", "1"].includes(
                                  config.outputs.irf?.shock_mode === "one_sd"
                                    ? "sd"
                                    : String(config.outputs.irf?.shock_size),
                                ) && (
                                  <option
                                    value={String(
                                      config.outputs.irf?.shock_size,
                                    )}
                                  >
                                    Custom shock
                                  </option>
                                )}
                              </select>
                            </Field>
                            <Field
                              label={`Custom shock (${shockUnits}; release to rerun)`}
                            >
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
                                    [
                                      "ArrowLeft",
                                      "ArrowRight",
                                      "Home",
                                      "End",
                                    ].includes(e.key) &&
                                    Number(e.currentTarget.value) !== 0
                                  )
                                    shock(
                                      "fixed",
                                      Number(e.currentTarget.value),
                                    );
                                }}
                              />
                            </Field>
                            <Field label="Bootstrap precision">
                              <select
                                data-testid="bootstrap-precision"
                                disabled={busy}
                                value={String(config.outputs.irf?.draws)}
                                onChange={(event) =>
                                  precision(Number(event.target.value))
                                }
                              >
                                <option value="200">
                                  Interactive · 200 draws
                                </option>
                                <option value="1000">
                                  Precise · 1,000 draws
                                </option>
                                {![200, 1000].includes(
                                  config.outputs.irf?.draws ?? 0,
                                ) && (
                                  <option value={config.outputs.irf?.draws}>
                                    Current ·{" "}
                                    {number(config.outputs.irf?.draws, 0)} draws
                                  </option>
                                )}
                              </select>
                            </Field>
                            <p className="small muted">
                              Precision changes rerun the seeded bootstrap.
                              Slider limits do not establish historical support.
                            </p>
                          </div>
                        </section>
                      )}
                    </section>
                  </div>
                </div>
              </div>
              <details className="secondary-section ">
                <summary>
                  Detailed diagnostics, samples, sources and provenance
                </summary>
                <ResultTableView
                  result={result}
                  manifest={manifest}
                  tab="samples"
                />
              </details>
            </section>
          </section>
        </Fragment>
      </ChartExportContext.Provider>
    </PrimaryChartProvider>
  );
}
