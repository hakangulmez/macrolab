import { useEffect, useMemo, useState } from "react";
import type { CountryBundle, Manifest } from "../types";
import {
  coverage,
  datasetCounts,
  region,
  regionNames,
  statuses,
  type CoverageCell,
} from "../uiData";
import { countryIndicators } from "../displayLabels";
import { csv, download, number, records, statusText, text } from "../format";
import { getCountry } from "../runtime";
import { CoverageLegend, CoverageMatrix } from "./CoverageMatrix";
import { Chart } from "./Chart";
import { Field, Status } from "./Common";
export default function DatasetExplorer({
  manifest,
  initialSelection,
  onUse,
}: {
  manifest: Manifest;
  initialSelection?: {
    country?: string;
    search?: string;
    category?: string;
    region?: string;
  };
  onUse: (country: string, concept: string) => void;
}) {
  const [query, setQuery] = useState(initialSelection?.search ?? ""),
    [area, setArea] = useState(initialSelection?.region ?? "All"),
    [group, setGroup] = useState(initialSelection?.category ?? "All"),
    [enabled, setEnabled] = useState(statuses),
    [countryQuery, setCountryQuery] = useState(
      manifest.countries.find((c) => c.iso3 === initialSelection?.country)
        ?.name ?? "",
    );
  const [selected, setSelected] = useState(
      `${initialSelection?.country ?? "EA"}:${manifest.indicators.some((i) => i.concept_id === initialSelection?.search) ? initialSelection!.search : "cpi"}`,
    ),
    [bundle, setBundle] = useState<CountryBundle | null>(null),
    [error, setError] = useState(""),
    [transform, setTransform] = useState("level");
  const [iso, concept] = selected.split(":");
  useEffect(() => {
    let active = true;
    void getCountry(iso)
      .then((b) => {
        if (active) {
          setBundle(b as unknown as CountryBundle);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [iso]);
  const cards = coverage(manifest),
    cell = cards.find((c) => c.country === iso && c.concept_id === concept);
  const card =
    bundle?.country.iso3 === iso
      ? bundle.cards.find((c) => c.concept_id === concept)
      : undefined;
  const countries = manifest.countries.filter(
    (c) =>
      (area === "All" || region(c) === area) &&
      `${c.name} ${c.iso3}`.toLowerCase().includes(countryQuery.toLowerCase()),
  );
  const indicators = manifest.indicators.filter(
    (i) =>
      (group === "All" || i.category === group) &&
      `${i.title} ${i.concept_id}`.toLowerCase().includes(query.toLowerCase()),
  );
  const title =
    countryIndicators(manifest.indicators, iso).find(
      (i) => i.concept_id === concept,
    )?.title ?? concept;
  const country = manifest.countries.find((c) => c.iso3 === iso);
  const points = useMemo(
    () =>
      ((bundle?.country.iso3 === iso ? bundle.series[concept] : []) ?? []).map(
        (r) => {
          const row = r as [string, number];
          return { period: row[0], value: row[1] };
        },
      ),
    [bundle, iso, concept],
  );
  const displayed = useMemo(() => {
    if (transform === "level") return points;
    const values = new Map(points.map((p) => [String(p.period), p.value]));
    return points.map((p) => {
      const prior =
          String(Number(String(p.period).slice(0, 4)) - 1) +
          String(p.period).slice(4),
        v = values.get(prior);
      return {
        ...p,
        value:
          typeof v === "number" && v !== 0 ? 100 * (p.value / v - 1) : null,
      };
    });
  }, [points, transform]);
  const segment = records(card?.source_segments)[0];
  const unit =
    transform === "yoy_pct"
      ? "Year-on-year change (%)"
      : text(segment?.unit_label ?? segment?.unit, "Source units");
  const counts = datasetCounts(manifest);
  function select(c: CoverageCell) {
    setSelected(`${c.country}:${c.concept_id}`);
    setTransform("level");
  }
  return (
    <section className="dataset-page stack" data-testid="screen-data">
      <div className="page-heading">
        <p className="overline">Dataset explorer</p>
        <h1>Find the series. See the limits.</h1>
        <p>
          {counts.populated.toLocaleString("en")} populated series across{" "}
          {counts.economies} economies. Every missing cell stays visible.
        </p>
      </div>
      <div className="dataset-layout">
        <aside
          className="dataset-filters card stack"
          aria-label="Filter the dataset"
        >
          <h2>Filter dataset</h2>
          <Field label="Find an economy">
            <input
              type="search"
              value={countryQuery}
              onChange={(e) => setCountryQuery(e.target.value)}
              placeholder="Name or code"
            />
          </Field>
          <Field label="Region">
            <select value={area} onChange={(e) => setArea(e.target.value)}>
              {["All", ...regionNames].map((r) => (
                <option key={r} value={r}>
                  {r} (
                  {
                    manifest.countries.filter(
                      (c) => r === "All" || region(c) === r,
                    ).length
                  }
                  )
                </option>
              ))}
            </select>
          </Field>
          <Field label="Indicator group">
            <select value={group} onChange={(e) => setGroup(e.target.value)}>
              {[
                "All",
                ...new Set(
                  manifest.indicators.map((i) => i.category ?? "Other"),
                ),
              ].map((g) => (
                <option key={g} value={g}>
                  {g} (
                  {
                    manifest.indicators.filter(
                      (i) => g === "All" || i.category === g,
                    ).length
                  }
                  )
                </option>
              ))}
            </select>
          </Field>
          <Field label="Find an indicator">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. CPI, GDP"
            />
          </Field>
          <fieldset>
            <legend>Coverage status</legend>
            {statuses.map((s) => (
              <label className="row status-filter" key={s}>
                <input
                  type="checkbox"
                  checked={enabled.includes(s)}
                  onChange={(e) =>
                    setEnabled(
                      e.target.checked
                        ? [...enabled, s]
                        : enabled.filter((v) => v !== s),
                    )
                  }
                />
                <span>
                  {statusText[s]} <small>({counts.statuses[s]})</small>
                </span>
              </label>
            ))}
          </fieldset>
          <p className="small">
            <i className="stale-dot" /> Amber dot: stale history
          </p>
          <button
            onClick={() => {
              setQuery("");
              setCountryQuery("");
              setArea("All");
              setGroup("All");
              setEnabled(statuses);
            }}
          >
            Reset filters
          </button>
        </aside>
        <div className="dataset-center card stack">
          <div>
            <p className="overline">Coverage at a glance</p>
            <h2>
              {countries.length} economies × {indicators.length} indicators
            </h2>
            <p className="small muted">
              Showing {countries.length} economies × {indicators.length}{" "}
              indicators; status filters dim excluded cells.
            </p>
          </div>
          <CoverageLegend manifest={manifest} />
          {countries.length && indicators.length ? (
            <CoverageMatrix
              manifest={manifest}
              countries={countries}
              indicators={indicators}
              selected={selected}
              onSelect={select}
              enabledStatuses={enabled}
            />
          ) : (
            <p role="status">
              No series match these filters. Reset to show the dataset.
            </p>
          )}
        </div>
        <aside
          className="series-inspector card stack"
          aria-label="Selected series"
          data-testid="series-inspector"
        >
          <div>
            <p className="overline">
              {country?.name} ·{" "}
              {
                manifest.indicators.find((i) => i.concept_id === concept)
                  ?.category
              }
            </p>
            <h2>{title}</h2>
          </div>
          {cell && <Status status={cell.status} />}
          <p className="small mono">
            {concept} · {iso}
          </p>
          {cell?.observations === 0 ? (
            <div className="info-box">
              This series is left missing. It is never filled from another
              country.
            </div>
          ) : (
            <>
              <div className="latest-value">
                <strong className="mono">
                  {number(displayed.at(-1)?.value, 2)}
                </strong>
                <span>
                  {unit} · {text(displayed.at(-1)?.period, "Loading…")}
                </span>
              </div>
              <Field label="Display transform">
                <select
                  value={transform}
                  onChange={(e) => setTransform(e.target.value)}
                >
                  <option value="level">Original source units</option>
                  <option value="yoy_pct">Year-on-year change (%)</option>
                </select>
              </Field>
              <Chart
                title={title}
                unit={unit}
                points={displayed}
                summary={`Observed ${title} for ${country?.name}. No imputation.`}
                estimateLabel="Observed"
                comparisonShortLabel=""
                xAxisTitle={`Period (${cell?.frequency === "M" ? "months" : cell?.frequency === "Q" ? "quarters" : "years"})`}
              />
            </>
          )}
          {error && <p role="alert">{error}</p>}
          <dl className="series-facts">
            {[
              ["Source", cell?.sources.join(", ")],
              ["Frequency", cell?.frequency],
              [
                "First → last",
                `${cell?.first_date ?? "—"} → ${cell?.last_date ?? "—"}`,
              ],
              ["Observations", cell?.observations],
              [
                "Freshness",
                cell?.stale
                  ? "Stale — history is not current"
                  : "See snapshot date and last observation",
              ],
              ["Adjustment", segment?.sa_flag],
              ["Definition", card?.definition],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dt>{text(label)}</dt>
                <dd>{text(value)}</dd>
              </div>
            ))}
          </dl>
          <p className="small">
            Actual modelling samples depend on complete common periods,
            transformations and lags. No displayed observation is substituted.
          </p>
          <div className="stack">
            <button
              className="primary"
              disabled={!cell?.observations}
              onClick={() => onUse(iso, concept)}
            >
              Use in analysis ↗
            </button>
            <button
              disabled={!points.length}
              onClick={() =>
                download(
                  csv([
                    ["date", concept],
                    ...points.map((p) => [p.period, p.value]),
                  ]),
                  `macrolab-${iso}-${concept}.csv`,
                  "text/csv",
                )
              }
            >
              Download CSV
            </button>
          </div>
          <details open>
            <summary>Source & citation</summary>
            {records(card?.source_segments).map((s, i) => (
              <p key={i} className="small citation">
                {text(s.attribution)}{" "}
                {typeof s.source_url === "string" && (
                  <a href={s.source_url} target="_blank" rel="noreferrer">
                    Official source ↗
                  </a>
                )}
              </p>
            ))}
          </details>
          <details>
            <summary>Complete source notes & metadata</summary>
            <pre>{JSON.stringify(card ?? cell, null, 2)}</pre>
          </details>
        </aside>
      </div>
    </section>
  );
}
