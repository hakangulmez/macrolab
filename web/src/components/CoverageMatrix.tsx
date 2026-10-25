import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import type { Country, Indicator, Manifest } from "../types";
import {
  coverage,
  region,
  sortedCountries,
  statuses,
  type CoverageCell,
} from "../uiData";
import { statusText } from "../format";
import { countryIndicators } from "../displayLabels";
const SHORT_LABELS: Record<string, string> = {
  gdp_real: "Real GDP",
  cons_priv: "Private consumption",
  gfcf: "Investment",
  cons_gov: "Government consumption",
  exports_real: "Exports",
  imports_real: "Imports",
  ind_prod: "Industrial production",
  retail_vol: "Retail sales",
  cli: "Leading indicator",
  cpi: "Consumer prices",
  cpi_core: "Core prices",
  ppi: "Producer prices",
  gdp_defl: "GDP deflator",
  house_real: "Real house prices",
  ulc: "Unit labour costs",
  unemp: "Unemployment rate",
  employment: "Employment",
  lfpr: "Participation rate",
  policy_rate: "Policy rate",
  rate_3m: "3-month rate",
  rate_10y: "10-year yield",
  term_spread: "Term spread",
  credit_pnfs: "Private credit",
  money_broad: "Broad money",
  equity_idx: "Share prices",
  reer: "Real effective FX",
  neer: "Nominal effective FX",
  fx_usd: "FX per USD",
  ca_gdp: "Current account",
  gov_debt: "Government debt",
  gov_balance: "Budget balance",
  conf_cons: "Consumer confidence",
  conf_bus: "Business confidence",
  oil_brent: "Brent oil",
  commod_idx: "Commodity prices",
  us_policy_rate: "US policy rate",
};
export function CoverageLegend({ manifest }: { manifest: Manifest }) {
  const cells = coverage(manifest);
  return (
    <div className="coverage-legend" aria-label="Coverage legend">
      {statuses.map((s) => (
        <span key={s}>
          <i className={`coverage-swatch ${s}`} />
          {statusText[s]}{" "}
          <b className="mono">{cells.filter((c) => c.status === s).length}</b>
        </span>
      ))}
      <span>
        <i className="stale-dot" /> Stale history
      </span>
    </div>
  );
}
export function CoverageMatrix({
  manifest,
  countries = manifest.countries,
  indicators = manifest.indicators,
  compact = false,
  selected,
  onSelect,
  enabledStatuses = statuses,
}: {
  manifest: Manifest;
  countries?: Country[];
  indicators?: Indicator[];
  compact?: boolean;
  selected?: string;
  onSelect?: (cell: CoverageCell) => void;
  enabledStatuses?: string[];
}) {
  const [anchor, setAnchor] = useState({ left: 12, top: 12 });
  const [hover, setHover] = useState<CoverageCell | null>(null),
    [table, setTable] = useState(false),
    [focus, setFocus] = useState(selected ?? "EA:cpi");
  useEffect(() => {
    if (compact || !selected || table) return;
    const cell = document.getElementById("coverage-" + selected);
    const scroll = cell?.closest<HTMLElement>(".matrix-scroll");
    if (cell && scroll) {
      const left =
        cell.getBoundingClientRect().left -
        scroll.getBoundingClientRect().left +
        scroll.scrollLeft;
      scroll.scrollLeft = Math.max(0, left - scroll.clientWidth / 2);
    }
  }, [selected, compact, table, countries, indicators]);
  const rows = useMemo(() => sortedCountries(countries), [countries]);
  const cols = useMemo(
    () =>
      [...indicators].sort(
        (a, b) =>
          String(a.category).localeCompare(String(b.category)) ||
          manifest.indicators.indexOf(a) - manifest.indicators.indexOf(b),
      ),
    [indicators, manifest.indicators],
  );
  const map = useMemo(
    () =>
      new Map(
        coverage(manifest).map((c) => [`${c.country}:${c.concept_id}`, c]),
      ),
    [manifest],
  );
  const description = (c: CoverageCell) => {
    const head = `${manifest.countries.find((x) => x.iso3 === c.country)?.name} · ${countryIndicators(manifest.indicators, c.country).find((i) => i.concept_id === c.concept_id)?.title} · ${statusText[c.status]}`;
    if (c.status === "missing" || !c.observations)
      return `${head} · no cleared source for this economy; never filled from another country`;
    return [
      head + (c.stale ? " · stale" : ""),
      c.frequency,
      `${c.first_date ?? "—"} → ${c.last_date ?? "—"}`,
      `${c.observations} observations`,
      c.sources.join(", "),
    ]
      .filter(Boolean)
      .join(" · ");
  };
  const visible = rows
    .flatMap((c) => cols.map((i) => map.get(`${c.iso3}:${i.concept_id}`)!))
    .filter((c) => c && enabledStatuses.includes(c.status));
  const active = visible.some((c) => `${c.country}:${c.concept_id}` === focus)
    ? focus
    : `${visible[0]?.country}:${visible[0]?.concept_id}`;
  function hoverCell(cell: CoverageCell, element: HTMLElement) {
    const bounds = element.getBoundingClientRect();
    setAnchor({
      left: Math.max(
        12,
        Math.min(
          bounds.left,
          window.innerWidth - Math.min(340, window.innerWidth - 24) - 12,
        ),
      ),
      top: Math.max(12, Math.min(bounds.bottom + 8, window.innerHeight - 180)),
    });
    setHover(cell);
  }
  function keys(e: KeyboardEvent<HTMLButtonElement>, ri: number, ci: number) {
    const offset: Record<string, [number, number]> = {
      ArrowRight: [0, 1],
      ArrowLeft: [0, -1],
      ArrowDown: [1, 0],
      ArrowUp: [-1, 0],
    };
    if (!offset[e.key]) return;
    e.preventDefault();
    const [dr, dc] = offset[e.key];
    let r = ri + dr,
      c = ci + dc;
    while (r >= 0 && r < rows.length && c >= 0 && c < cols.length) {
      const id = `${rows[r].iso3}:${cols[c].concept_id}`;
      const cell = map.get(id);
      if (cell && enabledStatuses.includes(cell.status)) {
        setFocus(id);
        document.getElementById("coverage-" + id)?.focus();
        break;
      }
      r += dr;
      c += dc;
    }
  }
  return (
    <div
      className={`coverage-block ${compact ? "compact-matrix" : "fit-matrix"}`}
    >
      <div className="row between">
        <p className="small muted">
          {compact
            ? "All economy–indicator cells"
            : "Arrow keys move between cells; Enter selects."}
        </p>
        <button
          className="link"
          aria-pressed={table}
          onClick={() => setTable(!table)}
        >
          {table ? "View as matrix" : "View as table"}
        </button>
      </div>
      <p className="scroll-cue">
        Scroll horizontally to explore every indicator →
      </p>
      <div
        className="matrix-scroll"
        tabIndex={0}
        aria-label="Coverage matrix, horizontally scrollable"
      >
        {table ? (
          <table className="coverage-table">
            <thead>
              <tr>
                <th>Economy</th>
                <th>Indicator</th>
                <th>Status</th>
                <th>Frequency</th>
                <th>First → last</th>
                <th>Observations</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((c) => (
                <tr key={`${c.country}:${c.concept_id}`}>
                  <th>
                    {manifest.countries.find((x) => x.iso3 === c.country)?.name}
                  </th>
                  <td>
                    {onSelect ? (
                      <button onClick={() => onSelect(c)}>
                        {
                          countryIndicators(
                            manifest.indicators,
                            c.country,
                          ).find((i) => i.concept_id === c.concept_id)?.title
                        }
                      </button>
                    ) : (
                      manifest.indicators.find(
                        (i) => i.concept_id === c.concept_id,
                      )?.title
                    )}
                  </td>
                  <td>
                    {statusText[c.status]}
                    {c.stale ? " · stale" : ""}
                  </td>
                  <td>{c.frequency}</td>
                  <td>
                    {c.first_date ?? "—"} → {c.last_date ?? "—"}
                  </td>
                  <td>{c.observations}</td>
                  <td>{c.sources.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="matrix-table">
            <thead>
              <tr>
                <th className="economy-cell">Economy / indicator</th>
                {cols.map((i, n) => (
                  <th
                    key={i.concept_id}
                    className={
                      cols[n - 1]?.category !== i.category ? "group-start" : ""
                    }
                  >
                    <span title={`${i.category}: ${i.title}`}>
                      {SHORT_LABELS[i.concept_id] ?? i.title.split(" (")[0]}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((country, ri) => (
                <tr
                  key={country.iso3}
                  className={
                    region(rows[ri - 1] ?? country) !== region(country) ||
                    ri === 0
                      ? "region-start"
                      : ""
                  }
                >
                  <th className="economy-cell">
                    {(region(rows[ri - 1] ?? country) !== region(country) ||
                      ri === 0) && <small>{region(country)}</small>}
                    {country.name}
                  </th>
                  {cols.map((indicator, ci) => {
                    const cell = map.get(
                      `${country.iso3}:${indicator.concept_id}`,
                    );
                    if (!cell) return <td key={indicator.concept_id} />;
                    const id = `${cell.country}:${cell.concept_id}`,
                      allowed = enabledStatuses.includes(cell.status);
                    const content = (
                      <>
                        <span className={`cell-fill ${cell.status}`} />
                        {cell.stale && <i className="stale-dot" />}
                      </>
                    );
                    return (
                      <td
                        key={id}
                        className={
                          cols[ci - 1]?.category !== indicator.category
                            ? "group-start"
                            : ""
                        }
                      >
                        {compact ? (
                          <span
                            className="coverage-cell"
                            onMouseEnter={(e) =>
                              hoverCell(cell, e.currentTarget)
                            }
                            onMouseLeave={() => setHover(null)}
                            title={description(cell)}
                          >
                            {content}
                          </span>
                        ) : (
                          <button
                            id={"coverage-" + id}
                            data-testid={"coverage-" + id}
                            aria-label={description(cell)}
                            aria-pressed={selected === id}
                            disabled={!allowed}
                            tabIndex={active === id ? 0 : -1}
                            className="coverage-cell"
                            onKeyDown={(e) => keys(e, ri, ci)}
                            onFocus={(e) => {
                              setFocus(id);
                              hoverCell(cell, e.currentTarget);
                            }}
                            onBlur={() => setHover(null)}
                            onMouseEnter={(e) =>
                              hoverCell(cell, e.currentTarget)
                            }
                            onMouseLeave={() => setHover(null)}
                            onClick={() => onSelect?.(cell)}
                          >
                            {content}
                          </button>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div
        className={`matrix-tooltip ${hover ? "is-hover" : ""}`}
        style={hover ? anchor : undefined}
        role="status"
        data-testid="coverage-tooltip"
      >
        {hover
          ? description(hover)
          : "Hover a cell for its status, sample and source. Missing observations are never imputed."}
      </div>
    </div>
  );
}
