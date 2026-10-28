import { sensitivityDisplayLabel } from "../sensitivityLabels";
import { useState, type ReactNode } from "react";
import type { CountryResult, Indicator, JsonRecord, Manifest } from "../types";
import { record, records, significant, text } from "../format";
import { Chart } from "./Chart";
import { Checks, DataTable, Field } from "./Common";
import { chartData, termLabel } from "../resultData";
import { countryIndicators } from "../displayLabels";
import { coefficientStars, reportedDF } from "../coefficientDisplay";

/** The same view projection is used in the primary and technical tables. */
export function PanelCovarianceTable({
  rows,
  lp,
  label,
  indicators,
}: {
  rows: JsonRecord[];
  lp: boolean;
  label: string;
  indicators: Indicator[];
}) {
  return (
    <DataTable
      caption={`${lp ? "90% pointwise intervals" : `${Number(rows[0]?.confidence_level ?? 0.95) * 100}% confidence intervals`} (${label})`}
      columns={[
        lp ? "Horizon" : "Term",
        "Estimate",
        "Std. error",
        "Lower",
        "Upper",
      ]}
      rows={rows.map((r) => ({
        [lp ? "Horizon" : "Term"]: lp
          ? r.horizon
          : termLabel(text(r.term), indicators),
        Estimate: r.estimate,
        "Std. error": r.std_error,
        // Same normal critical value as the existing 90% LP bands;
        // this only displays bounds from the reported sensitivity SE.
        Lower: lp
          ? Number(r.estimate) - 1.6448536269514722 * Number(r.std_error)
          : r.lower,
        Upper: lp
          ? Number(r.estimate) + 1.6448536269514722 * Number(r.std_error)
          : r.upper,
      }))}
    />
  );
}

export function PanelResults({
  result,
  manifest,
  selectedCountry,
  onCountryChange,
  chartControls,
}: {
  chartControls?: ReactNode;
  result: CountryResult;
  manifest: Manifest;
  selectedCountry?: string;
  onCountryChange?: (country: string) => void;
}) {
  const [selected, setSelected] = useState("");
  const [countryCovariance, setCountryCovariance] = useState("HAC(4)");
  if (!result.model_id.startsWith("panel.") || result.status !== "ok")
    return null;
  const panel = record(result.panel),
    samples = record(panel.country_samples),
    estimates = record(
      countryCovariance === "conventional" && result.model_id === "panel.fe"
        ? panel.country_estimates_conventional
        : panel.country_estimates,
    );
  const countries = Object.keys(samples),
    country = countries.includes(selectedCountry ?? selected)
      ? (selectedCountry ?? selected)
      : countries[0];
  const name = (code: string) =>
    manifest.countries.find((c) => c.iso3 === code)?.name ?? code;
  const lp = result.model_id === "panel.lp",
    chart = chartData(result, manifest.indicators)[0];
  const countryRows = records(estimates[country]);
  const coefficients = records(result.coefficients_table);
  const displayRow = (r: JsonRecord) => ({
    Term: termLabel(text(r.term), manifest.indicators),
    Pooled: r,
    ...Object.fromEntries(
      countries.map((c) => [
        name(c),
        records(estimates[c]).find((x) => x.term === r.term),
      ]),
    ),
  });
  const covid = coefficients.filter((r) => /^covid_/.test(text(r.term)));
  const cell = (r: JsonRecord, key: string) => {
    if (key === "Term") return text(r[key]);
    const row = record(r[key]);
    const code = countries.find((c) => name(c) === key);
    const df =
      key === "Pooled"
        ? Number(panel.df_resid)
        : reportedDF(row, Number(record(samples[code ?? ""]).nobs));
    return (
      <>
        <span>
          {significant(row.estimate)}
          <sup>{coefficientStars(row, df)}</sup>
        </span>
        <span className="coefficient-se">({significant(row.std_error)})</span>
      </>
    );
  };
  const outcome =
    countryIndicators(manifest.indicators, country)
      .find((i) => i.concept_id === chart?.variable)
      ?.title.split(" · ")[0] ?? chart?.name;
  const outcomeUnit =
    chart?.unit === "cumulative % change in the level" &&
    ["cpi", "cpi_core"].includes(chart.variable ?? "")
      ? "cumulative % change in the price level"
      : chart?.unit;
  return (
    <section className="card stack" data-testid="panel-results">
      <h2>
        {lp
          ? "Pooled and country responses"
          : "Pooled and country coefficients"}
      </h2>
      <p>
        N = {text(panel.N)} · T min–max = {text(panel.T_min)}–
        {text(panel.T_max)} · {text(panel.total_observations)} observations ·{" "}
        {text(panel.effects).replaceAll("_", " ")} effects ·{" "}
        {text(panel.covariance)}
      </p>
      <p className="small muted">
        Within R²{lp ? " (horizon 0)" : ""}:{" "}
        {significant(panel.within_r_squared)}.{" "}
        {lp
          ? "Country LPs use exactly the pooled model's country-specific anchor dates. The pooled slope restricts coefficients to be common."
          : "Country OLS columns allow separate slopes and intercepts. Pooled coefficients impose common slopes; two-way FE additionally remove common time effects."}
      </p>
      {typeof panel.first_stage_largest_root === "number" && (
        <p>
          First-stage largest root:{" "}
          {significant(panel.first_stage_largest_root)}.{" "}
          {text(panel.generated_regressor_uncertainty)}
        </p>
      )}
      {!lp && (
        <Field label="Country OLS covariance">
          <select
            value={countryCovariance}
            onChange={(e) => setCountryCovariance(e.target.value)}
          >
            <option value="HAC(4)">HAC(4) · Newey–West</option>
            <option value="conventional">Conventional</option>
          </select>
        </Field>
      )}
      {!lp && (
        <DataTable
          caption={`Coefficients · standard errors in parentheses. Pooled: ${text(panel.covariance)}; country OLS: ${countryCovariance}. Two-sided t tests: *** p < 0.01; ** p < 0.05; * p < 0.10.`}
          rows={coefficients
            .filter((r) => !/^covid_/.test(text(r.term)))
            .map(displayRow)}
          columns={["Term", "Pooled", ...countries.map(name)]}
          renderCell={cell}
          expandGroups
          stickyFirst
          groups={
            covid.length
              ? [
                  {
                    label: `COVID dummies (${covid.length})`,
                    rows: covid.map(displayRow),
                  },
                ]
              : []
          }
        />
      )}
      {lp && chart && (
        <>
          <Chart
            primary
            controls={
              <>
                {chartControls}{" "}
                <Field label="Overlay country">
                  <select
                    value={country}
                    onChange={(e) => {
                      setSelected(e.target.value);
                      onCountryChange?.(e.target.value);
                    }}
                  >
                    {countries.map((c) => (
                      <option key={c} value={c}>
                        {name(c)}
                      </option>
                    ))}
                  </select>
                </Field>
              </>
            }
            title={`Pooled response of ${outcome} and ${name(country)}`}
            unit={outcomeUnit ?? chart.unit}
            summary="Solid blue: pooled response with 68% pointwise panel band. Dashed orange: country LP on identical estimation dates. These are different slope restrictions, not an agreement count."
            points={chart.points.map((p, i) => ({
              ...p,
              comparison: Number(countryRows[i]?.estimate),
            }))}
            comparisonLabel={`${name(country)} · matched sample`}
            estimateLabel="Pooled"
            comparisonShortLabel={name(country)}
            intervalLabel={`68% pointwise (${text(panel.covariance)})`}
          />
        </>
      )}
      {lp && panel.effects === "two_way" && (
        <p className="small muted">
          Country LP curves omit pooled time effects; they share estimation
          dates but use a different nuisance specification.
        </p>
      )}
      <h3>Actual country samples</h3>
      <DataTable
        rows={countries.map((c) => ({
          Country: name(c),
          Start: record(samples[c]).start,
          End: record(samples[c]).end,
          Observations: record(samples[c]).nobs,
        }))}
      />
      <section>
        <h3>Fixed effects and sample details</h3>
        {!lp && (
          <DataTable
            caption={`Full pooled coefficients, including COVID dummies · ${Number(coefficients[0]?.confidence_level ?? 0.95) * 100}% confidence intervals (${text(panel.covariance)})`}
            columns={["Term", "Estimate", "Std. error", "Lower", "Upper"]}
            rows={coefficients.map((r) => ({
              Term: termLabel(text(r.term), manifest.indicators),
              Estimate: r.estimate,
              "Std. error": r.std_error,
              Lower: r.lower,
              Upper: r.upper,
            }))}
          />
        )}
        <DataTable
          countries={manifest.countries}
          rows={records(panel.fixed_effect_summary)}
        />
        <details>
          <summary>Exact country sample metadata</summary>
          <pre>{JSON.stringify(samples, null, 2)}</pre>
        </details>
      </section>
      <h3>Covariance sensitivity · same point estimates</h3>
      {result.sensitivity.variants.map((variant, i) => (
        <section key={i}>
          <h3>{sensitivityDisplayLabel(variant)}</h3>
          <Checks
            countries={manifest.countries}
            checks={(variant.checks ?? []) as CountryResult["checks"]}
          />
          <PanelCovarianceTable
            rows={records(variant.rows)}
            lp={lp}
            label={sensitivityDisplayLabel(variant)}
            indicators={manifest.indicators}
          />
        </section>
      ))}
    </section>
  );
}
