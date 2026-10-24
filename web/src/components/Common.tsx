import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { Check, Country, Indicator, JsonRecord } from "../types";
import { tableValue, statusText, text } from "../format";
import {
  checkContext,
  findingContext,
  type Finding,
  readableCheckMessage,
  warningTiers,
  resultDisclosureChecks,
} from "./warnings";
import "./warnings.css";
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Status({ status }: { status: string }) {
  return (
    <span className={`status ${status}`}>{statusText[status] ?? status}</span>
  );
}
export function Checks({
  checks,
  onFix,
  onSourceCard,
  indicators = [],
  countries = [],
  showEstimationPhase = false,
  previouslyDisplayedChecks,
}: {
  checks: Check[];
  onFix?: (fix: JsonRecord) => void;
  onSourceCard?: (country: string, conceptId: string) => void;
  indicators?: Indicator[];
  countries?: Country[];
  showEstimationPhase?: boolean;
  previouslyDisplayedChecks?: Check[];
}) {
  const tiers = warningTiers(checks);
  const disclosed = resultDisclosureChecks(checks, previouslyDisplayedChecks);
  const noteCount = tiers.notes.length + tiers.sourceFindings.length;
  const actions = (check: Check) => (
    <>
      {check.fix && onFix && (
        <button
          className="link"
          onClick={() => onFix({ concept_id: check.concept_id, ...check.fix })}
        >
          Apply suggested change
        </button>
      )}
      {check.country && check.concept_id && onSourceCard && (
        <button
          className="link"
          onClick={() => onSourceCard(check.country!, check.concept_id!)}
        >
          View series card
        </button>
      )}
    </>
  );
  const list = (items: Finding[]) => (
    <ul className="warning-items">
      {items.map((check, index) => (
        <li key={`${check.code}-${check.country}-${check.concept_id}-${index}`}>
          <div className="warning-item-text">
            {findingContext(check, countries, indicators) && (
              <span className="warning-context">
                {findingContext(check, countries, indicators)}
              </span>
            )}
            {showEstimationPhase &&
              check.instances.some((instance) => disclosed.has(instance)) && (
                <span className="warning-phase">Found after estimation</span>
              )}
            <span>{readableCheckMessage(check, indicators)}</span>
          </div>
          {check.instances.length === 1 && actions(check.instances[0])}
          <details className="warning-technical">
            <summary>Technical details</summary>
            {check.instances.length > 1 &&
              [
                ...new Map(
                  check.instances.map((instance) => [
                    JSON.stringify([
                      instance.country,
                      instance.concept_id,
                      instance.fix,
                    ]),
                    instance,
                  ]),
                ).values(),
              ].map((instance, i) => (
                <div key={i}>
                  {checkContext(instance, countries, indicators)}{" "}
                  {actions(instance)}
                </div>
              ))}
            <pre>{JSON.stringify(check.instances, null, 2)}</pre>
          </details>
        </li>
      ))}
    </ul>
  );
  return (
    <section className="analysis-checks" aria-label="Analysis checks">
      {showEstimationPhase && checks.length > 0 && (
        <p className="small muted">
          Builder checks coverage first. Running adds prepared-data diagnostics
          and fitted-model checks. The labels identify newly reported findings
          or fitted-model checks; technical details record when each check was
          computed.
        </p>
      )}
      {tiers.blocking.length > 0 && (
        <section
          className="warning-tier warning-blocking"
          aria-label="Blocking checks"
        >
          <h3>Blocking · {tiers.blocking.length}</h3>
          <p>Resolve these before an estimate can be produced.</p>
          {list(tiers.blocking)}
        </section>
      )}
      {tiers.importantCount > 0 && (
        <section
          className="warning-tier warning-important"
          aria-label="Important warnings"
        >
          <h3>Important · {tiers.importantCount}</h3>
          {list(tiers.important)}
          {tiers.moreImportant.length > 0 && (
            <details className="warning-overflow">
              <summary>
                {tiers.moreImportant.length} more important warnings
              </summary>
              {list(tiers.moreImportant)}
            </details>
          )}
        </section>
      )}
      {noteCount > 0 && (
        <details className="warning-tier warning-notes">
          <summary>
            Notes ·{" "}
            {tiers.sourceFindings.length > 0
              ? `${tiers.sourceFindings.length} source notes`
              : `${tiers.notes.length} analysis notes`}
            {tiers.sourceNotes.length > 0 && tiers.notes.length > 0
              ? ` · ${tiers.notes.length} analysis notes`
              : ""}
          </summary>
          {tiers.sourceNotes.length > 0 && (
            <div className="source-note-group">
              <p>
                <strong>
                  {tiers.sourceNotes.length}{" "}
                  {tiers.sourceNotes.length === 1
                    ? "series has"
                    : "series have"}{" "}
                  source notes.
                </strong>{" "}
                Review definitions, coverage and provider caveats in the series
                cards.
              </p>
              <ul className="source-note-links">
                {tiers.sourceNotes.map((note, index) => (
                  <li key={`${note.country}-${note.concept_id}-${index}`}>
                    {onSourceCard && note.country && note.concept_id ? (
                      <button
                        className="link"
                        onClick={() =>
                          onSourceCard(note.country!, note.concept_id!)
                        }
                      >
                        {checkContext(note, countries, indicators)}
                      </button>
                    ) : (
                      <span>
                        {checkContext(note, countries, indicators) ||
                          "Source information"}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              {list(tiers.sourceFindings)}
            </div>
          )}
          {tiers.notes.length > 0 && list(tiers.notes)}
        </details>
      )}
      {!tiers.blocking.length && !tiers.importantCount && !noteCount && (
        <p className="small">
          No blocking checks found for this selection. Assumptions still apply.
        </p>
      )}
    </section>
  );
}
export function DataTable({
  rows,
  columns,
  countries = [],
  caption,
  renderCell,
  groups = [],
  stickyFirst = false,
}: {
  rows: JsonRecord[];
  columns?: string[];
  countries?: Country[];
  caption?: string;
  renderCell?: (row: JsonRecord, column: string) => ReactNode;
  groups?: { label: string; rows: JsonRecord[] }[];
  stickyFirst?: boolean;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState(false);
  const [expanded, setExpanded] = useState<string[]>([]);
  useEffect(() => {
    const element = wrap.current;
    if (!element) return;
    const observer = new ResizeObserver(() =>
      setOverflow(element.scrollWidth > element.clientWidth + 1),
    );
    observer.observe(element);
    if (element.firstElementChild) observer.observe(element.firstElementChild);
    return () => observer.disconnect();
  }, []);
  const keys =
    columns ??
    Array.from(
      new Set([...rows, ...groups.flatMap((g) => g.rows)].flatMap(Object.keys)),
    ).filter((k) =>
      rows.some((r) => ["string", "number", "boolean"].includes(typeof r[k])),
    );
  const sticky = stickyFirst || /^country$/i.test(keys[0] ?? "");
  const body = (data: JsonRecord[]) =>
    data.map((r, i) => (
      <tr key={i}>
        {keys.map((k) => (
          <td key={k}>
            {renderCell
              ? renderCell(r, k)
              : /country/i.test(k) && typeof r[k] === "string"
                ? (countries.find((c) => c.iso3 === r[k])?.name ?? text(r[k]))
                : tableValue(
                    k === "value" && typeof r.diagnostic === "string"
                      ? r.diagnostic
                      : k,
                    r[k],
                  )}
          </td>
        ))}
      </tr>
    ));
  return (
    <div className="data-table">
      {(overflow || stickyFirst) && (
        <p className="small muted table-scroll-cue">
          ↔ Scroll horizontally to see all columns.
          {sticky && " The first column stays fixed."}
        </p>
      )}
      <div
        ref={wrap}
        className={`table-wrap${sticky ? " sticky-first" : ""}${stickyFirst ? " wide-country-table" : ""}`}
        tabIndex={0}
        role="region"
        aria-label={caption ?? "Scrollable data table"}
      >
        <table>
          {caption && <caption>{caption}</caption>}
          <thead>
            <tr>
              {keys.map((k) => (
                <th scope="col" key={k}>
                  {k.replaceAll("_", " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body(rows)}
            {groups.map((g) => (
              <Fragment key={g.label}>
                <tr className="table-group">
                  <td colSpan={keys.length}>
                    <button
                      className="link"
                      aria-expanded={expanded.includes(g.label)}
                      onClick={() =>
                        setExpanded((current) =>
                          current.includes(g.label)
                            ? current.filter((v) => v !== g.label)
                            : [...current, g.label],
                        )
                      }
                    >
                      {expanded.includes(g.label) ? "▾" : "▸"} {g.label}
                    </button>
                  </td>
                </tr>
                {expanded.includes(g.label) && body(g.rows)}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
