import { useState } from "react";
import { countryIndicators } from "../displayLabels";
import type { CountryResult, Manifest } from "../types";
import { record, records, significant, text, title } from "../format";
import { chartData } from "../resultData";
import { Chart } from "./Chart";
import { DataTable, Field } from "./Common";

export function BvarResults({
  result,
  manifest,
}: {
  result: CountryResult;
  manifest: Manifest;
}) {
  const [mode, setMode] = useState("both"),
    [variable, setVariable] = useState(0),
    [band, setBand] = useState("0.68");
  if (result.model_id !== "bvar.minn" || result.status !== "ok" || !result.irf)
    return null;
  const b = record(result.bvar),
    prior = record(b.prior),
    draws = record(b.draws),
    ols = record(b.matched_ols);
  const indicators = countryIndicators(manifest.indicators, result.country);
  const charts = chartData(result, indicators),
    chart = charts[variable] ?? charts[0];
  const intervals = record(record(b.bands)[band]),
    lo = intervals.lower as number[][],
    hi = intervals.upper as number[][];
  const olsValues = ols.values as number[][] | undefined,
    means = record(prior.own_first_lag_mean),
    scales = record(prior.ar_residual_scales);
  const points = chart.points.map((p, i) => ({
    ...p,
    value: mode === "var" ? (olsValues?.[i][variable] ?? null) : p.value,
    lower: mode === "var" ? undefined : lo[i][variable],
    upper: mode === "var" ? undefined : hi[i][variable],
    comparison: mode === "both" ? olsValues?.[i][variable] : undefined,
  }));
  return (
    <section className="card stack" data-testid="bvar-results">
      <h2>Bayesian VAR and matched OLS VAR</h2>
      <p>
        λ = {significant(prior.lambda_)} · {text(b.lambda_selection)} tightness
        · {text(draws.requested)} seeded draws · {text(draws.retained)}{" "}
        retained. Largest root ≥ 1: {text(draws.explosive)} (
        {significant(Number(draws.explosive_share) * 100)}%). Excluded:{" "}
        {text(draws.dropped)}.
      </p>
      <p className="small muted">
        The conjugate prior treats own and cross-variable lags symmetrically.
        Comparison uses the same sample, controls, recursive ordering and
        physical shock. It compares shrinkage assumptions, not independent
        identification.
      </p>
      <div
        className="segmented"
        role="group"
        aria-label="BVAR and OLS comparison"
      >
        {["bvar", "var", "both"].map((m) => (
          <button
            key={m}
            className={mode === m ? "primary" : ""}
            aria-pressed={mode === m}
            disabled={m !== "bvar" && ols.status !== "ok"}
            onClick={() => setMode(m)}
          >
            {m === "both" ? "Both" : m === "bvar" ? "BVAR" : "OLS VAR"}
          </button>
        ))}
      </div>
      {ols.status !== "ok" && (
        <p role="status">OLS comparison blocked: {text(ols.reason)}</p>
      )}
      <div className="two-fields">
        <Field label="BVAR response variable">
          <select
            value={variable}
            onChange={(e) => setVariable(Number(e.target.value))}
          >
            {charts.map((c, i) => (
              <option key={c.variable} value={i}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Posterior band">
          <select value={band} onChange={(e) => setBand(e.target.value)}>
            <option value="0.68">68% posterior credible band</option>
            <option value="0.9">90% posterior credible band</option>
          </select>
        </Field>
      </div>
      <div className="legend">
        <span>
          <i className="legend-line" />
          {mode === "var" ? "OLS VAR point estimate" : "BVAR posterior median"}
        </span>
        {mode !== "var" && (
          <span>
            <i className="legend-band" />
            {Number(band) * 100}% posterior credible band
          </span>
        )}
        {mode === "both" && (
          <span>
            <i className="legend-line comparison" />
            Matched OLS VAR point estimate
          </span>
        )}
      </div>
      <Chart
        title={`${chart.name} · ${mode === "var" ? "OLS VAR" : "BVAR"}`}
        unit={chart.unit}
        points={points}
        intervalLabel={`${Number(band) * 100}% posterior credible band`}
        comparisonLabel="Matched OLS VAR"
        summary={
          mode === "var"
            ? "OLS point response; no OLS uncertainty band is displayed here."
            : `Posterior median and ${Number(band) * 100}% pointwise credible band, conditional on the chosen hyperparameters. ${Number(draws.dropped) > 0 ? "Conditioned on stability after explicit draw exclusion." : "Explosive draws retained."}`
        }
      />
      <DataTable
        caption="Prior means and univariate AR(p) residual scales (SSE / residual degrees of freedom)"
        columns={["Variable", "Own first-lag mean", "AR residual SD"]}
        rows={result.irf.variables.map((name) => ({
          Variable: title(name, indicators),
          "Own first-lag mean": String(means[name]),
          "AR residual SD": scales[name],
        }))}
      />
      <p className="small muted">
        Lag variance decay: {text(prior.lag_decay)}. Diffuse deterministic prior
        variance: {Number(prior.constant_variance).toLocaleString()}.
        Sum-of-coefficients: {prior.sum_of_coefficients ? "On" : "Off"}.
        Co-persistence: {prior.co_persistence ? "On" : "Off"}. Grid selection is
        empirical Bayes; hyperparameter uncertainty is not integrated out.
      </p>
      {b.lambda_selection === "grid" && (
        <DataTable
          caption="Marginal-likelihood grid · selected λ maximizes the conditional log marginal likelihood"
          columns={["λ", "Log marginal likelihood", "Selected"]}
          rows={records(b.grid).map((r) => ({
            λ: r.lambda,
            "Log marginal likelihood": Number(
              r.log_marginal_likelihood,
            ).toFixed(2),
            Selected: r.selected ? "Selected" : "—",
          }))}
        />
      )}
      <details>
        <summary>FEVD · posterior mean variance shares</summary>
        <DataTable
          rows={(record(result.fevd).values as number[][][]).flatMap(
            (period, h) =>
              period.map((row, j) => ({
                Horizon: h + 1,
                Response: title(result.irf!.variables[j], indicators),
                ...Object.fromEntries(
                  row.map((v, k) => [
                    title(result.irf!.variables[k], indicators),
                    v,
                  ]),
                ),
              })),
          )}
        />
      </details>
    </section>
  );
}
