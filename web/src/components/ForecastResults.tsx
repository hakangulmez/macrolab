import { ResultDataTable as DataTable } from "./ResultDataTable";
import { lazy, Suspense, useContext, useEffect, useState } from "react";
import { ChartExportContext } from "../chartExportContext";
import { countryIndicators } from "../displayLabels";
import { record, records, significant, text, title } from "../format";
import { chartData, forecastErrorChart } from "../resultData";
import type { CountryResult, Manifest } from "../types";
import { Chart } from "./Chart";
import { Field } from "./Common";
import { forecastModel } from "../forecast";
import { exportPng } from "../pngExport";

const ForecastViews = lazy(() =>
  import("./AdditionalViews").then((m) => ({ default: m.ForecastViews })),
);

export function ForecastResults({
  result,
  manifest,
  first = true,
}: {
  result: CountryResult;
  manifest: Manifest;
  first?: boolean;
}) {
  const [variable, setVariable] = useState(0),
    [band, setBand] = useState("0.9"),
    [errorModel, setErrorModel] = useState("ARIMA"),
    [evaluationView, setEvaluationView] = useState("errors");
  const context = useContext(ChartExportContext);
  const [exportError, setExportError] = useState("");
  useEffect(() => {
    if (
      !first ||
      !context ||
      !forecastModel(result.model_id) ||
      result.status !== "ok"
    )
      return;
    const handler = (event: Event) => {
      const data = record(result.forecast);
      const evaluation = record(result.evaluation);
      const base =
        result.evaluation && evaluationView === "errors"
          ? (evaluation.horizons as number[]).map((h) =>
              forecastErrorChart(result, errorModel, h),
            )
          : chartData(result, manifest.indicators);
      const all = base.map((c) => {
        const interval = record(
          record(record(record(data.distributions)[c.variable ?? ""]).bands)[
            band
          ],
        );
        return {
          ...c,
          intervalLabel: result.evaluation
            ? evaluationView === "errors"
              ? "Actual minus prediction"
              : "Relative RMSE"
            : `${Number(band) * 100}% predictive interval`,
          points: c.points.map((p) => {
            const i =
              (data.periods as string[] | undefined)?.indexOf(
                String(p.period),
              ) ?? -1;
            return i < 0
              ? p
              : {
                  ...p,
                  lower: (interval.lower as number[])[i],
                  upper: (interval.upper as number[])[i],
                };
          }),
        };
      });
      const selected =
        (event as CustomEvent<{ mode?: string }>).detail?.mode === "panel"
          ? all
          : [all[variable] ?? all[0]];
      setExportError("");
      void exportPng(selected, {
        ...context,
        forecast: true,
        horizon: false,
        intervalLabel: selected[0]?.intervalLabel,
        estimateLabel: result.evaluation
          ? evaluationView === "errors"
            ? errorModel
            : "Error metric"
          : "Predictive mean",
        comparisonLabel: result.evaluation
          ? "Random walk"
          : context.comparisonLabel,
        bandLevel: Number(band),
        note: selected[0]?.pngNote
          ? undefined
          : (data.assumptions as string[] | undefined)?.join(" "),
      }).catch((error) => setExportError(String(error)));
    };
    window.addEventListener("macrolab-export-png", handler);
    return () => window.removeEventListener("macrolab-export-png", handler);
  }, [
    first,
    context,
    result,
    manifest.indicators,
    variable,
    band,
    errorModel,
    evaluationView,
  ]);
  if (!forecastModel(result.model_id) || result.status !== "ok") return null;
  const f = record(result.forecast),
    e = record(result.evaluation),
    indicators = countryIndicators(manifest.indicators, result.country);
  const charts =
      result.evaluation && evaluationView === "errors"
        ? (e.horizons as number[]).map((h) =>
            forecastErrorChart(result, errorModel, h),
          )
        : chartData(result, indicators),
    chart = charts[variable] ?? charts[0];
  const distribution = record(record(f.distributions)[chart?.variable ?? ""]);
  const intervals = record(record(distribution.bands)[band]);
  const periods = f.periods as string[] | undefined;
  const points =
    chart?.points.map((p) => {
      const i = periods?.indexOf(String(p.period)) ?? -1;
      return i < 0
        ? p
        : {
            ...p,
            lower: (intervals.lower as number[])[i],
            upper: (intervals.upper as number[])[i],
          };
    }) ?? [];
  const arima = record(f.arima),
    chosen = record(arima.chosen),
    runner = record(arima.runner_up);
  const metricRows = (rows: unknown) =>
    records(rows).map((r) => ({
      Model: r.model,
      Horizon: r.horizon,
      RMSE: r.rmse,
      MAE: r.mae,
      "RMSE / random walk": r.relative_rmse,
      "Forecast count": r.n_forecasts,
    }));
  return (
    <section className="card stack" data-testid="forecast-results">
      {exportError && <p role="alert">{exportError}</p>}
      <h2>
        {result.model_id === "fc.eval"
          ? "Forecast evaluation"
          : `${text(f.method)} forecast`}
      </h2>
      <p>
        {result.model_id === "fc.eval"
          ? text(e.label)
          : "Final-vintage data; real-time performance may be worse."}
      </p>
      {result.model_id === "fc.eval" ? (
        <>
          <Suspense fallback={<p>Loading forecast views…</p>}>
            <ForecastViews
              manifest={manifest}
              result={result}
              snapshot={context?.snapshot ?? manifest.snapshot_id}
            />
          </Suspense>
          <h3>
            {title(text(e.target), indicators)} · {text(e.unit)}
          </h3>
          <p>
            {text(e.order_policy)}. {text(e.successful_origins)} of{" "}
            {text(e.attempted_origins)} origins succeeded.
          </p>
          <DataTable
            caption={`Paired common origins · errors in ${e.unit === "percentage points of year-on-year HICP inflation" ? "percentage points of inflation" : "original units"}`}
            columns={[
              "Model",
              "Horizon",
              "RMSE",
              "MAE",
              "RMSE / random walk",
              "Forecast count",
            ]}
            rows={metricRows(e.metrics)}
          />
          <details>
            <summary>Pairwise Diebold–Mariano / HLN tests</summary>
            <p>
              Squared-error loss; h−1 calendar autocovariances, HLN correction
              and t reference. Several pairwise tests are not a joint test.
              Negative variance estimates use Bartlett weights and are flagged.
            </p>
            <DataTable
              rows={records(e.dm_tests).map((r) => ({
                "Model A": r.model_a,
                "Model B": r.model_b,
                Horizon: r.horizon,
                "DM / HLN": r.statistic,
                "p value": r.p_value,
                "Forecast count": r.n,
                "Variance weights": r.bartlett_fallback
                  ? "Bartlett fallback"
                  : "Unweighted",
                Status: r.status,
              }))}
            />
          </details>
          {result.sensitivity.variants.map((v) => (
            <details key={text(v.id)}>
              <summary>{text(v.label)}</summary>
              <p>
                Only the scoring rows are excluded. Training prefixes and
                forecasts are unchanged.
              </p>
              <DataTable rows={metricRows(v.metrics)} />
            </details>
          ))}
          <Field label="Evaluation chart">
            <select
              value={evaluationView}
              onChange={(event) => setEvaluationView(event.target.value)}
            >
              <option value="errors">Forecast error by target date</option>
              <option value="metrics">Relative RMSE</option>
            </select>
          </Field>
          {evaluationView === "errors" && (
            <Field label="Error model">
              <select
                value={errorModel}
                onChange={(event) => setErrorModel(event.target.value)}
              >
                {(e.models as string[])
                  .filter((m) => m !== "Random walk")
                  .map((m) => (
                    <option key={m}>{m}</option>
                  ))}
              </select>
            </Field>
          )}
        </>
      ) : (
        <>
          <p>
            Origin: {text(f.origin)} · original units · future COVID dummies are
            zero.
          </p>
          {arima.chosen && (
            <p>
              Chosen ARIMA ({(chosen.order as number[]).join(", ")}) × (
              {(chosen.seasonal_order as number[]).join(", ")}); AICc{" "}
              {significant(chosen.aicc)}. Runner-up:{" "}
              {runner.order
                ? `(${(runner.order as number[]).join(", ")}) × (${(runner.seasonal_order as number[]).join(", ")}); AICc ${significant(runner.aicc)}`
                : "none (fixed order or no other converged candidate)"}
              . Ljung–Box at lag {text(record(arima.ljung_box).lag)}: p ={" "}
              {significant(record(arima.ljung_box).p_value)}.
            </p>
          )}
          <Field label="Predictive interval">
            <select value={band} onChange={(e) => setBand(e.target.value)}>
              <option value="0.68">68% predictive interval</option>
              <option value="0.9">90% predictive interval</option>
            </select>
          </Field>
          <p className="small">{text(f.interval_scope)}</p>
        </>
      )}
      {charts.length > 1 && (
        <Field
          label={
            result.model_id === "fc.eval"
              ? "Evaluation horizon"
              : "Forecast variable"
          }
        >
          <select
            value={variable}
            onChange={(e) => setVariable(Number(e.target.value))}
          >
            {charts.map((c, i) => (
              <option key={i} value={i}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      {chart && (
        <Chart
          title={chart.name}
          unit={chart.unit}
          points={points}
          bar={chart.bar}
          comparisonLabel="Random walk"
          estimateLabel={
            points.some((p) => p.comparison !== undefined)
              ? errorModel
              : chart.bar
                ? "Relative RMSE"
                : "Predictive mean"
          }
          comparisonShortLabel="Random walk"
          intervalLabel={`${Number(band) * 100}% predictive interval`}
          summary={chart.summary}
          xAxisTitle={chart.xAxisTitle}
          pngNote={
            chart.pngNote ?? (f.assumptions as string[] | undefined)?.join(" ")
          }
          exportContext={
            context && {
              ...context,
              forecast: true,
              horizon: false,
              intervalLabel:
                result.model_id === "fc.eval"
                  ? evaluationView === "errors"
                    ? "Actual minus prediction"
                    : "Relative RMSE"
                  : `${Number(band) * 100}% predictive interval`,
              estimateLabel:
                result.model_id === "fc.eval"
                  ? evaluationView === "errors"
                    ? errorModel
                    : "Error metric"
                  : "Predictive mean",
              note: chart.pngNote
                ? undefined
                : (f.assumptions as string[] | undefined)?.join(" "),
            }
          }
        />
      )}
      {Boolean(f.assumptions) && (
        <ul>
          {(f.assumptions as string[]).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      {Boolean(f.distributions) && (
        <p className="small muted">{text(distribution.inverse_method)}</p>
      )}
      {result.sensitivity.variants
        .filter((v) => v.id === "d0")
        .map((v) => (
          <details key="d0">
            <summary>d = 0 sensitivity · {text(v.status)}</summary>
            {v.status === "ok" ? (
              <DataTable
                rows={(record(v.distribution).mean as number[]).map(
                  (value, i) => ({
                    Horizon: i + 1,
                    Mean: value,
                    Lower: (
                      record(record(record(v.distribution).bands)["0.9"])
                        .lower as number[]
                    )[i],
                    Upper: (
                      record(record(record(v.distribution).bands)["0.9"])
                        .upper as number[]
                    )[i],
                  }),
                )}
                caption="d = 0 · 90% predictive interval in original units"
              />
            ) : (
              <p>{text(v.reason)}</p>
            )}
          </details>
        ))}
    </section>
  );
}
