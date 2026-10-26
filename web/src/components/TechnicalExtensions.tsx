import { useContext, useEffect, useRef, useState } from "react";
import { AnalysisRuntime, buildBundle } from "../runtime";
import type {
  AnalysisConfig,
  AnalysisResult,
  JsonRecord,
  Manifest,
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
  transforms,
} from "../format";
import { ChartExportContext } from "../chartExportContext";
import { countryIndicators } from "../displayLabels";
import { Chart } from "./Chart";
import { Checks, DataTable, Field } from "./Common";

export function TechnicalExtensions({
  config,
  runtime,
  busy,
  manifest,
}: {
  config: AnalysisConfig;
  runtime: AnalysisRuntime;
  busy: boolean;
  manifest: Manifest;
}) {
  const hd =
    ["var.ols", "ident.recursive", "out.hd"].includes(config.model.id) &&
    Boolean(config.identification);
  const crisis = config.model.params.template_id === "tur_pass_through";
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [variable, setVariable] = useState("");
  const [country, setCountry] = useState(config.countries[0]);
  const inherited = useContext(ChartExportContext);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  if (!hd && !crisis) return null;
  function request() {
    const c = structuredClone(config);
    if (hd) {
      if (c.model.id !== "out.hd") c.model.params.hd_match_var = true;
      c.model.id = "out.hd";
      c.comparison.enabled = false;
    } else c.model.params.crisis_extension = true;
    return c;
  }
  async function compute(python = false) {
    setError("");
    setPending(true);
    try {
      const c = request(),
        bundle = await buildBundle(c);
      if (python) {
        const script = await runtime.exportPython(c, bundle);
        if (alive.current)
          download(
            script,
            `macrolab-${hd ? "hd" : "crisis"}.py`,
            "text/x-python",
          );
      } else {
        const next = await runtime.run(c, bundle);
        if (alive.current) setResult(next as unknown as AnalysisResult);
      }
    } catch (e) {
      if (alive.current) setError(String(e));
    } finally {
      if (alive.current) setPending(false);
    }
  }
  const row =
    result?.results.find((r) => r.country === country) ?? result?.results[0];
  const accounting = record(row?.historical_decomposition);
  const names = (accounting.variables ?? []) as string[];
  const selected = names.includes(variable) ? variable : names[0];
  const j = names.indexOf(selected);
  const periods = (accounting.periods ?? []) as string[];
  const actual = (accounting.actual ?? []) as number[][];
  const contributions = (accounting.contributions ?? []) as number[][][];
  const initial = (accounting.initial_condition ?? []) as number[][];
  const deterministic = (accounting.deterministic ?? []) as number[][];
  const colors = [
    "#0e7490",
    "#c2570c",
    "#7e22ce",
    "#15803d",
    "#a16207",
    "#be123c",
  ];
  const indicators = countryIndicators(manifest.indicators, country);
  const stack = names.map((name, k) => ({
    name: title(name, indicators) + " shock",
    color: colors[k % colors.length],
    values: periods.map((_, t) => contributions[t][j][k]),
  }));
  if (periods.length)
    stack.push({
      name: "Initial condition + deterministic",
      color: "#64748b",
      values: periods.map((_, t) => initial[t][j] + deterministic[t][j]),
    });
  const extension = record(result?.crisis_analysis);
  const variants = records(extension.rows);
  const baseline = records(record(result?.results[0]?.pass_through).horizons);
  const sample = record(extension.sample_2003);
  const comparisons = [
    {
      id: "baseline",
      label: "Baseline",
      pass: baseline,
      sample: row?.actual_sample,
      status: row?.status,
    },
    {
      id: "sample_2003",
      label: "January 2003 onward",
      pass: records(
        record((sample.pass_through as JsonRecord[] | undefined)?.[0]).horizons,
      ),
      sample: record(records(sample.summary)[0]).sample,
      status: sample.status,
    },
    ...variants.map((v) => {
      const r = records(v.results)[0];
      return {
        id: text(v.variant_id),
        label: text(v.label),
        pass: records(record(r?.pass_through).horizons),
        sample: r?.actual_sample,
        status: v.status,
      };
    }),
  ];
  const summaries = records(extension.agreement);
  const change = (id: string, horizon: unknown) =>
    records(summaries.find((s) => s.horizon === horizon)?.variants).find(
      (v) => v.variant_id === id,
    );
  const materialLabel = (id: string, horizon: unknown) =>
    change(id, horizon)?.changes_answer_materially
      ? "changes the answer materially"
      : id === "baseline"
        ? "Baseline"
        : change(id, horizon)
          ? "No change greater than 50%"
          : "Not assessable";
  const variantLabel = (id: unknown) =>
    comparisons.find((v) => v.id === id)?.label ??
    (id === "lags_6" ? "6 lags" : id === "hac" ? "HAC inference" : text(id));
  const ratioRows = comparisons.flatMap((v) =>
    v.pass
      .filter((p) => [6, 12, 24].includes(Number(p.horizon)))
      .map((p) => ({
        Specification: v.label,
        Months: p.horizon,
        Ratio: significant(p.ratio),
        "Magnitude sensitivity": materialLabel(v.id, p.horizon),
        "68% interval": `${significant(record(record(p.bands)["0.68"]).lower)} to ${significant(record(record(p.bands)["0.68"]).upper)}`,
        "NEER response (%)": significant(p.fx_cumulative),
        Observations: p.nobs,
        Sample: `${record(v.sample).start}–${record(v.sample).end}`,
        "Weak denominator": p.denominator_weak ? "Yes" : "No",
      })),
  );
  function exportCSV() {
    const rows: JsonRecord[] = hd
      ? periods.flatMap((period, t) =>
          names.map((name, k) => ({
            period,
            variable: name,
            actual: actual[t][k],
            initial_condition: initial[t][k],
            deterministic: deterministic[t][k],
            ...Object.fromEntries(
              names.map((shock, s) => [
                "shock_" + shock,
                contributions[t][k][s],
              ]),
            ),
          })),
        )
      : comparisons.flatMap((v) =>
          v.pass.map((p) => ({
            specification: v.label,
            ...p,
            magnitude_assessment: materialLabel(v.id, p.horizon),
            sample: v.sample,
          })),
        );
    const keys = [...new Set(rows.flatMap(Object.keys))];
    download(
      csv([
        keys,
        ...rows.map((r) =>
          keys.map((k) =>
            typeof r[k] === "object" ? JSON.stringify(r[k]) : r[k],
          ),
        ),
      ]),
      `macrolab-${hd ? "hd" : "crisis"}.csv`,
      "text/csv",
    );
  }
  return (
    <section
      className="card stack"
      data-testid={hd ? "hd-view" : "crisis-view"}
    >
      <h2>{hd ? "Historical decomposition" : "Türkiye crisis sensitivity"}</h2>
      <p>
        {hd
          ? "Account for the observed transformed series under the same recursive ordering. This is model-based accounting, not causal attribution."
          : "Optional analysis with the approved crisis windows: February–December 2001, August–December 2018 and September 2021–June 2023. The original result and agreement counts remain unchanged."}
      </p>
      <div className="row">
        <button disabled={busy || pending} onClick={() => void compute()}>
          {pending
            ? "Computing…"
            : hd
              ? "Compute historical decomposition"
              : "Compute crisis analysis"}
        </button>
        {pending && (
          <button
            onClick={() => {
              runtime.cancel();
              setResult(null);
            }}
          >
            Cancel extension
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {result && (
        <>
          <Checks
            checks={result.checks}
            showEstimationPhase
            countries={manifest.countries}
            indicators={indicators}
          />
          {hd && periods.length > 0 && (
            <>
              <div className="row">
                <Field label="HD country">
                  <select
                    aria-label="HD country"
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                  >
                    {config.countries.map((code) => (
                      <option key={code} value={code}>
                        {manifest.countries.find((c) => c.iso3 === code)
                          ?.name ?? code}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="HD variable">
                  <select
                    aria-label="HD variable"
                    value={selected}
                    onChange={(e) => setVariable(e.target.value)}
                  >
                    {names.map((name) => (
                      <option key={name} value={name}>
                        {title(name, indicators)}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <p>
                Largest companion root:{" "}
                {number(accounting.companion_spectral_radius, 4)} ·
                Reconstruction maximum absolute error:{" "}
                {Number(accounting.maximum_identity_error)
                  .toExponential(1)
                  .replace("e-", "e−")}
                .
              </p>
              <Chart
                estimateLabel="Actual"
                comparisonShortLabel=""
                title={`Historical decomposition · ${title(selected, indicators)}`}
                unit={
                  transforms[
                    text(
                      record(row?.actual_sample.transforms[selected]).transform,
                    )
                  ] ?? "transformed units"
                }
                points={periods.map((period, t) => ({
                  period,
                  value: actual[t][j],
                }))}
                stack={stack}
                summary={text(accounting.label)}
                exportContext={
                  inherited && {
                    ...inherited,
                    analysis: "Historical decomposition",
                    country:
                      manifest.countries.find((c) => c.iso3 === country)
                        ?.name ?? country,
                    sample: `Accounting: ${periods[0]}–${periods.at(-1)} · n = ${periods.length} · Snapshot ${result.snapshot_id}`,
                    horizon: false,
                    estimateLabel: "Actual",
                  }
                }
              />
              <p className="small">
                The first{" "}
                {Array.isArray(accounting.initial_periods)
                  ? accounting.initial_periods.length
                  : 0}{" "}
                periods initialise the VAR. CSV retains initial conditions and
                deterministic contributions separately for every variable.
              </p>
            </>
          )}
          {crisis && (
            <>
              <p>
                Joint HC1 sandwich delta-method intervals, including
                numerator/denominator covariance. Near-zero denominators make
                ratios unreliable.
              </p>
              <DataTable rows={ratioRows} />
              {variants.map((v) => (
                <div key={text(v.variant_id)}>
                  <strong>
                    {text(v.label)}: {text(v.status)}
                  </strong>
                  <Checks
                    checks={(v.checks ?? []) as AnalysisResult["checks"]}
                    countries={manifest.countries}
                    indicators={indicators}
                    showEstimationPhase
                  />
                </div>
              ))}
              <p>{text(extension.agreement_rule)}</p>
              <DataTable
                rows={summaries
                  .filter((r) => [6, 12, 24].includes(Number(r.horizon)))
                  .map((r) => ({
                    Months: r.horizon,
                    "Same-sign specifications": `${r.same_sign} / ${r.eligible}`,
                    "Ratio range (including baseline)": `${significant(r.ratio_min)} to ${significant(r.ratio_max)}`,
                    "Changes the answer materially":
                      records(r.variants)
                        .filter((v) => v.changes_answer_materially)
                        .map((v) => variantLabel(v.variant_id))
                        .join(", ") || "None",
                  }))}
              />
              <details>
                <summary>
                  Full samples, excluded periods, controls and all horizons
                </summary>
                <pre>{JSON.stringify(extension, null, 2)}</pre>
              </details>
            </>
          )}
          <div className="row">
            <button onClick={exportCSV}>Extension CSV</button>
            <button
              disabled={pending || busy}
              onClick={() => void compute(true)}
            >
              Extension Python
            </button>
            <button
              onClick={() =>
                download(
                  JSON.stringify(result, null, 2),
                  `macrolab-${hd ? "hd" : "crisis"}.json`,
                  "application/json",
                )
              }
            >
              Extension JSON
            </button>
          </div>
        </>
      )}
    </section>
  );
}
