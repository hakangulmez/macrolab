import { ResultDataTable as DataTable } from "./ResultDataTable";
import { useContext, useEffect, useMemo, useState } from "react";
import { ChartExportContext } from "../chartExportContext";
import { diagnosticModel } from "../diagnosticModels";
import { Chart } from "./Chart";
import { exportPng } from "../pngExport";
import type { CountryResult, Manifest } from "../types";
import { record, records, significant, text, title } from "../format";
import { Field } from "./Common";
import { countryIndicators } from "../displayLabels";
import { chartData, termLabel } from "../resultData";
const probability = (value: unknown) =>
  typeof value === "number" && value < 0.001 ? "<0.001" : significant(value);
export function DiagnosticResults({
  result,
  manifest,
  first = true,
}: {
  result: CountryResult;
  manifest: Manifest;
  first?: boolean;
}) {
  const [selected, setSelected] = useState(0),
    [band, setBand] = useState("0.68"),
    [error, setError] = useState("");
  const inherited = useContext(ChartExportContext);
  const indicatorsForChart = countryIndicators(
    manifest.indicators,
    result.country,
  );
  const vecm = record(result.vecm),
    shock = result.irf?.variables.indexOf(result.irf.shock) ?? 0;
  const bandData = record(record(vecm.bands)[band]);
  const charts = chartData(result, indicatorsForChart).map((chart, j) =>
    !result.vecm
      ? chart
      : {
          ...chart,
          intervalLabel: Number(vecm.draws)
            ? `${Number(band) * 100}% pointwise bootstrap band`
            : "No bands",
          summary:
            "Recursive response to one structural standard deviation. VECM responses can be permanent and need not return to zero.",
          unit:
            chart.transformation === "log level"
              ? "100 × log response (approximately %)"
              : chart.unit,
          points: chart.points.map((p, h) => {
            const scale = chart.transformation === "log level" ? 100 : 1;
            const lower = (bandData.lower as number[][][] | undefined)?.[h]?.[
              j
            ]?.[shock];
            const upper = (bandData.upper as number[][][] | undefined)?.[h]?.[
              j
            ]?.[shock];
            return {
              ...p,
              value: p.value === null ? null : p.value * scale,
              lower: lower === undefined ? undefined : lower * scale,
              upper: upper === undefined ? undefined : upper * scale,
            };
          }),
        },
  );
  const intervalLabel = charts[selected]?.intervalLabel;
  const context = useMemo(
    () =>
      inherited && {
        ...inherited,
        country:
          manifest.countries.find((c) => c.iso3 === result.country)?.name ??
          result.country,
        sample: `${result.actual_sample.start}–${result.actual_sample.end} · n = ${result.actual_sample.nobs}`,
        horizon: Boolean(result.vecm),
        bandLevel: Number(band),
        comparisonLabel: "95% critical value",
        intervalLabel,
        estimateLabel: result.vecm ? "Response" : "Test statistic",
      },
    [
      inherited,
      manifest.countries,
      result.country,
      result.actual_sample,
      result.vecm,
      band,
      intervalLabel,
    ],
  );
  useEffect(() => {
    if (
      !diagnosticModel(result.model_id) ||
      !context ||
      !first ||
      !charts.length ||
      result.status !== "ok"
    )
      return;
    const handler = (event: Event) => {
      const chosen =
        (event as CustomEvent<{ mode?: string }>).detail?.mode === "panel"
          ? charts
          : [charts[selected] ?? charts[0]];
      setError("");
      void exportPng(chosen, context).catch((e) => setError(String(e)));
    };
    window.addEventListener("macrolab-export-png", handler);
    return () => window.removeEventListener("macrolab-export-png", handler);
  }, [context, first, charts, selected, result.status, result.model_id]);
  if (result.status !== "ok" || (!result.cointegration && !result.break_tests))
    return null;
  const c = record(result.cointegration),
    v = record(result.vecm),
    b = record(result.break_tests),
    indicators = countryIndicators(manifest.indicators, result.country);
  const matrix = (values: unknown, errors?: unknown) =>
    ((values ?? []) as number[][]).map((row, i) => ({
      Variable: title((c.variables as string[])[i], indicators),
      ...Object.fromEntries(
        row.map((value, j) => [
          `Relation ${j + 1}`,
          errors
            ? `${significant(value)} (${significant((errors as number[][])[i][j])})`
            : value,
        ]),
      ),
    }));
  return (
    <section className="card stack" data-testid="diagnostic-results">
      {error && <p role="alert">{error}</p>}
      {result.cointegration ? (
        <>
          <h2>Cointegration and long-run relations</h2>
          <p>
            {text(c.deterministic_case)}. VAR lags {text(c.var_lags)}; lagged
            differences {text(c.lagged_differences)}.
          </p>
          <p>
            Suggested rank: <strong>{text(c.suggested_rank)}</strong> ·
            sequential trace test at 95%. {text(c.caveat)}
          </p>
          <DataTable
            caption="Johansen tests · asymptotic critical values"
            columns={[
              "Null rank",
              "Trace",
              "Trace 90%",
              "Trace 95%",
              "Trace 99%",
              "Maximum eigenvalue",
              "Max eigen 90%",
              "Max eigen 95%",
              "Max eigen 99%",
            ]}
            rows={records(c.johansen).map((r) => ({
              "Null rank": r.null_rank,
              Trace: r.trace,
              "Trace 90%": record(r.trace_critical)["90"],
              "Trace 95%": record(r.trace_critical)["95"],
              "Trace 99%": record(r.trace_critical)["99"],
              "Maximum eigenvalue": r.maximum_eigenvalue,
              "Max eigen 90%": record(r.max_eigen_critical)["90"],
              "Max eigen 95%": record(r.max_eigen_critical)["95"],
              "Max eigen 99%": record(r.max_eigen_critical)["99"],
            }))}
          />
          {records(c.engle_granger).length > 0 && (
            <>
              <p>{text(c.normalisation_note)}</p>
              <DataTable
                caption="Engle–Granger · MacKinnon p-values"
                rows={records(c.engle_granger).map((r) => ({
                  "Dependent variable": title(text(r.dependent), indicators),
                  Regressor: title(text(r.regressor), indicators),
                  Trend: r.trend_label,
                  Statistic: r.statistic,
                  "p value": probability(r.p_value),
                }))}
              />
            </>
          )}
          {result.vecm && (
            <>
              <h3>VECM · chosen rank {text(v.rank)}</h3>
              <p>
                {text(v.normalisation)} {text(v.permanence_note)}
              </p>
              <DataTable
                caption="Normalised β · asymptotic standard errors in parentheses"
                rows={matrix(v.beta, v.beta_std_error)}
              />
              <DataTable
                caption="Adjustment speeds α · asymptotic standard errors in parentheses"
                rows={matrix(v.alpha, v.alpha_std_error)}
              />
              <details>
                <summary>Short-run Γ and deterministic coefficients</summary>
                <DataTable
                  rows={((v.gamma ?? []) as number[][]).flatMap((row, i) =>
                    row.map((value, j) => ({
                      Outcome: title((c.variables as string[])[i], indicators),
                      Regressor: title(
                        (c.variables as string[])[
                          j % (c.variables as string[]).length
                        ],
                        indicators,
                      ),
                      Lag: Math.floor(j / (c.variables as string[]).length) + 1,
                      Estimate: value,
                      "Std. error": (v.gamma_std_error as number[][])[i][j],
                    })),
                  )}
                />
              </details>
              <p>
                {text(v.draws)} seeded bootstrap draws.{" "}
                {Number(v.draws)
                  ? text(v.inference)
                  : "Bootstrap disabled; point responses only."}{" "}
                Ordering:{" "}
                {(v.order as string[])
                  .map((name) => title(name, indicators))
                  .join(" → ")}
                .
              </p>
            </>
          )}
        </>
      ) : (
        <>
          <h2>Structural-break diagnostics</h2>
          <p>
            q = {text(b.tested_coefficients)} tested coefficients. Scale:
            Wald/q. Sup-F covariance: {text(b.covariance)}
            {b.covariance === "HAC" ? ` (${text(b.hac_lags)} lags)` : ""}.
            Search trims 15% at each end. {text(b.inference_label)}.
            {b.minimum_segment_observations !== undefined && (
              <>
                {" "}
                Minimum trimmed segment: {text(
                  b.minimum_segment_observations,
                )}{" "}
                observations (
                {significant(b.minimum_segment_observations_per_coefficient)}{" "}
                per tested coefficient).
              </>
            )}
          </p>
          <p>
            Peak date: <strong>{text(record(b.supremum).date)}</strong> · sup-F{" "}
            {significant(record(b.supremum).f_statistic)} ·{" "}
            {text(record(b.supremum).p_value_method)} p ={" "}
            {probability(record(b.supremum).p_value)}.
          </p>
          <DataTable
            caption={`${text(b.critical_source)} · q = ${text(b.tested_coefficients)} · Wald/q scale`}
            rows={[
              {
                "90% critical value": record(b.critical_values)["90"],
                "95% critical value": record(b.critical_values)["95"],
                "99% critical value": record(b.critical_values)["99"],
              },
            ]}
          />
          <DataTable
            caption={`Calibration sensitivity · q = ${text(b.tested_coefficients)} · statistic and critical value: Wald/q · 499 seeded bootstrap draws`}
            columns={[
              "Calibration",
              "Selected",
              "Peak date",
              "Sup-F",
              "p value",
              "95% critical value",
              "Reject at 5%",
            ]}
            rows={records(b.inference_variants).map((r) => ({
              Calibration: r.label,
              Selected: r.selected ? "Selected" : "",
              "Peak date": r.date,
              "Sup-F": r.f_statistic,
              "p value": probability(r.p_value),
              "95% critical value": record(r.critical_values)["95"],
              "Reject at 5%": r.reject_5pct ? "Yes" : "No",
            }))}
          />
          <p className="small">
            {text(record(b.bootstrap).serial_correlation_note)}
          </p>
          {record(b.chow).status === "ok" ? (
            <DataTable
              caption={`User-selected date · Chow uses conventional covariance; fixed-date Wald uses host ${text(b.host_covariance)} covariance · Wald scale (not divided by q)`}
              rows={[
                {
                  Date: record(b.chow).date,
                  "Chow F": record(b.chow).classical_chow_f,
                  "Chow p value": probability(record(b.chow).classical_chow_p),
                  "Wald statistic": record(b.chow).wald,
                  "Wald p value": probability(record(b.chow).pointwise_wald_p),
                },
              ]}
            />
          ) : (
            <p>
              Select a Chow break date in the Builder to test a specific date.
            </p>
          )}
          <p>
            CUSUM uses {records(b.recursive).length} recursive residuals after{" "}
            {text(b.recursive_burn)} initial rows; its bounds assume the
            recursive-regression conditions.
          </p>
          <details>
            <summary>Tested coefficients and omitted candidate dates</summary>
            <p>
              {(b.tested_terms as string[])
                .map((name) => termLabel(name, indicators))
                .join(", ")}
            </p>
            <DataTable rows={records(b.omitted_candidates)} />
          </details>
          <ul>
            {(b.notes as string[]).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </>
      )}
      {charts.length > 0 && (
        <>
          <Field label="Diagnostic chart">
            <select
              value={selected}
              onChange={(e) => setSelected(Number(e.target.value))}
            >
              {charts.map((c, i) => (
                <option key={c.name} value={i}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          {result.vecm && Number(vecm.draws) > 0 && (
            <Field label="VECM band">
              <select value={band} onChange={(e) => setBand(e.target.value)}>
                <option value="0.68">68% pointwise bootstrap</option>
                <option value="0.9">90% pointwise bootstrap</option>
              </select>
            </Field>
          )}
          <Chart
            {...(charts[selected] ?? charts[0])}
            title={(charts[selected] ?? charts[0]).name}
            comparisonLabel="95% critical value"
            estimateLabel={result.vecm ? "Response" : "Test statistic"}
            comparisonShortLabel="95% critical value"
            exportContext={context ?? undefined}
          />
        </>
      )}
    </section>
  );
}
