import type { ReactNode } from "react";
import type { Check, Country, Indicator, JsonRecord } from "../types";
import { number, statusText, text } from "../format";
import {
  checkContext,
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
  const noteCount = tiers.notes.length + tiers.sourceNotes.length;
  const list = (items: Check[]) => (
    <ul className="warning-items">
      {items.map((check, index) => (
        <li key={`${check.code}-${check.country}-${check.concept_id}-${index}`}>
          <div className="warning-item-text">
            {checkContext(check, countries, indicators) && (
              <span className="warning-context">
                {checkContext(check, countries, indicators)}
              </span>
            )}
            {showEstimationPhase && disclosed.has(check) && (
              <span className="warning-phase">Found after estimation</span>
            )}
            <span>{readableCheckMessage(check, indicators)}</span>
          </div>
          {check.fix && onFix && (
            <button
              className="link"
              onClick={() =>
                onFix({ concept_id: check.concept_id, ...check.fix })
              }
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
          <details className="warning-technical">
            <summary>Technical details</summary>
            <pre>{JSON.stringify(check, null, 2)}</pre>
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
            {tiers.sourceNotes.length > 0
              ? `${tiers.sourceNotes.length} source notes`
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
                    {showEstimationPhase &&
                      note.checks.some((check) => disclosed.has(check)) && (
                        <span className="warning-phase">
                          Found after estimation
                        </span>
                      )}
                    <details className="warning-technical">
                      <summary>Technical details</summary>
                      <pre>{JSON.stringify(note.checks, null, 2)}</pre>
                    </details>
                  </li>
                ))}
              </ul>
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
}: {
  rows: JsonRecord[];
  columns?: string[];
}) {
  const keys =
    columns ??
    Array.from(new Set(rows.flatMap(Object.keys)))
      .filter((k) =>
        rows.some((r) => ["string", "number", "boolean"].includes(typeof r[k])),
      )
      .slice(0, 8);
  return (
    <div
      className="table-wrap"
      tabIndex={0}
      role="region"
      aria-label="Scrollable data table"
    >
      <table>
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
          {rows.map((r, i) => (
            <tr key={i}>
              {keys.map((k) => (
                <td key={k}>
                  {typeof r[k] === "number" ? number(r[k], 6) : text(r[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
