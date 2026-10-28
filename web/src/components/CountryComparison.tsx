import { useEffect, useState } from "react";
import type { AnalysisResult, CountryBundle, Manifest } from "../types";
import type { ResultChart } from "../resultData";
import { countryPanels } from "../comparisonData";
import { number, record, records, text } from "../format";
import { exportPng } from "../pngExport";
import { getTemplateSources } from "../runtime";
import { Chart } from "./Chart";
import { DataTable, Field } from "./Common";

export function CountryComparison({
  result,
  manifest,
  bundles,
  compact,
  country,
  selectCountry,
}: {
  result: AnalysisResult;
  manifest: Manifest;
  bundles: Record<string, CountryBundle>;
  compact: boolean;
  country: string;
  selectCountry: (code: string) => void;
}) {
  const [response, setResponse] = useState("gdp_real");
  const [error, setError] = useState("");
  const all = countryPanels(result, manifest);
  const current = all.filter((c) => c.variable === response);
  const selectedName =
    manifest.countries.find((c) => c.iso3 === country)?.name ?? country;
  const summary = records(result.template_summary).filter(
    (r) => r.response === response,
  );
  const ranked = [...summary].sort((a, b) => Number(b.peak) - Number(a.peak));
  const ranking: ResultChart = {
    name: "Peak responses · descriptive ranking",
    unit: current[0]?.unit ?? "response units",
    coefficient: true,
    xAxisTitle: "Country",
    intervalLabel: "68% pointwise interval at the selected peak",
    points: ranked.map((r) => ({
      period:
        manifest.countries.find((c) => c.iso3 === r.country)?.name ??
        text(r.country),
      value: Number(r.peak),
      lower: Number(r.lower),
      upper: Number(r.upper),
    })),
    summary:
      "Overlapping intervals do not support a ranking. Peaks are selected separately across horizons; no equality test or simultaneous ranking inference is performed.",
  };
  useEffect(() => {
    const handler = () => {
      const sources = Object.values(bundles)
        .filter((b) => result.config.countries.includes(b.country.iso3))
        .flatMap((b) =>
          b.cards
            .filter(
              (c) =>
                result.config.series.some(
                  (s) => s.concept_id === c.concept_id,
                ) && c.concept_id !== "policy_rate",
            )
            .flatMap((c) =>
              records(c.source_segments).map((s) => text(s.source)),
            ),
        );
      void getTemplateSources(String(result.config.model.params.policy_measure))
        .then((extra) =>
          exportPng(all, {
            snapshot: result.snapshot_id,
            analysis: "Same ECB shock · country comparison",
            country: result.config.countries.join(" / "),
            sample:
              "Actual LP samples shown in each panel; shared y-axis within each response.",
            scenario: `${result.config.model.params.policy_measure === "dfr" ? "DFR" : result.config.model.params.policy_measure === "rate_3m" ? "EA 3-month" : "BIS EA"} shock: +${number(Number(record(result.magnitude_note).shock_size ?? result.results[0]?.irf?.shock_size), 2)} pp${record(record(record(result.config.model.params.first_stage).outputs).irf).shock_mode === "one_sd" ? " (one SD)" : ""} · ${result.config.model.params.displayed_band} bands`,
            frequency: "Q",
            horizon: true,
            sources: [
              ...new Set([...sources, ...extra.map((c) => text(c.source))]),
            ],
            bandLevel: 0.68,
            comparisonLabel: "",
            note: `${text(result.magnitude_note, "")} Selected peaks are descriptive; overlapping intervals do not support a ranking. ${result.config.model.params.displayed_band === "conditional" ? "Conditional bands ignore first-stage uncertainty." : "Joint bands re-estimate both stages on the common window."}`,
          }),
        )
        .catch((e) => setError(String(e)));
    };
    window.addEventListener("macrolab-export-png", handler);
    return () => window.removeEventListener("macrolab-export-png", handler);
  }, [all, bundles, result]);
  const controls = (
    <div className="row">
      <Field label="Compare response">
        <select
          aria-label="Compare response"
          value={response}
          onChange={(e) => setResponse(e.target.value)}
        >
          {[
            ...new Map(
              all.map((c) => [
                c.variable,
                c.name.split(" · ").slice(1).join(" · "),
              ]),
            ).entries(),
          ].map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Country">
        <select
          data-testid="comparison-country"
          value={country}
          onChange={(e) => selectCountry(e.target.value)}
        >
          {result.results.map((r) => (
            <option key={r.country} value={r.country}>
              {manifest.countries.find((c) => c.iso3 === r.country)?.name ??
                r.country}
            </option>
          ))}
        </select>
      </Field>
    </div>
  );
  return (
    <section className="stack" data-testid="country-comparison">
      <h2>One ECB shock, {result.results.length} national responses</h2>
      <p className="small muted">
        Shared y-axis for each response · 68% pointwise{" "}
        {String(result.config.model.params.displayed_band)} bands.{" "}
        {result.config.model.params.displayed_band === "conditional" &&
          "These bands ignore first-stage estimation uncertainty."}
      </p>
      <div className="charts-grid">
        {current
          .filter((c) => !compact || c.name.startsWith(selectedName + " · "))
          .map((c) => (
            <Chart
              primary={c.name.startsWith(selectedName + " · ")}
              controls={
                c.name.startsWith(selectedName + " · ") ? controls : undefined
              }
              estimateLabel="Response"
              comparisonShortLabel=""
              key={c.name}
              {...c}
              title={c.name}
            />
          ))}
      </div>
      <Chart
        estimateLabel="Response"
        comparisonShortLabel=""
        {...ranking}
        title={ranking.name}
      />
      <details className="secondary-section">
        <summary>Detailed diagnostics, samples, sources and provenance</summary>
        <h3>Per-country estimation samples</h3>
        <DataTable
          countries={manifest.countries}
          rows={summary.map((r) => {
            const sample = record(r.sample);
            return {
              Country: r.country,
              Start: sample.start,
              End: sample.end,
              Observations: sample.nobs,
              "Peak horizon": r.horizon,
              "Peak response": r.peak,
            };
          })}
        />
      </details>
      {error && <p role="alert">PNG export failed: {error}</p>}
    </section>
  );
}
