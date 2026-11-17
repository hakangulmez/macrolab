import { Fragment, useState } from "react";
import {
  chronologyCoverage,
  chronologyForCountry,
  reportCountries,
  reportCountryNames,
  resultReportCountries,
  timelineForResult,
  timelineHighlights,
  type ReportCountry,
  type ReportTopic,
} from "../reportTimeline";
import type { AnalysisResult } from "../types";
import "./report-timeline.css";

const topicNames: Record<ReportTopic, string> = {
  inflation: "Inflation",
  policy_rate: "Interest rates",
  growth: "Growth & activity",
  labour: "Employment & wages",
  credit: "Credit & financial conditions",
  exchange_rate: "Exchange rates",
  fiscal: "Fiscal policy",
  trade: "Trade & external balance",
};
function dateLabel(value: string, year = false) {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    ...(year ? { year: "numeric" } : {}),
    timeZone: "UTC",
  });
}

export function EconomicTimeline() {
  return <ReportTimeline />;
}

export function ReportTimeline({ result }: { result?: AnalysisResult }) {
  const standalone = !result;
  const available = result
    ? resultReportCountries(result)
    : [...reportCountries];
  const [scope, setScope] = useState<"analysis" | "archive">(
    standalone ? "archive" : "analysis",
  );
  const [selectedCountry, setSelectedCountry] = useState<ReportCountry>(
    available[0] ?? "USA",
  );
  const [selectedYear, setSelectedYear] = useState("all");
  const [topic, setTopic] = useState<ReportTopic | "all">("all");
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);
  const country =
    scope === "archive" || available.includes(selectedCountry)
      ? selectedCountry
      : available[0];
  const context =
    scope === "archive"
      ? chronologyForCountry(country)
      : result
        ? timelineForResult(result, undefined, country)
        : null;
  if (!available.length || !context) return null;
  const activeTopic = context.topics.includes(topic as ReportTopic)
    ? topic
    : "all";
  const matching = context.notes.filter((note) => {
    const haystack = [
      note.title,
      note.summary,
      note.kind,
      note.actor,
      note.source.institution,
      note.source.quote,
      ...(note.source.passages?.map((passage) => passage.quote) ?? []),
    ]
      .join(" ")
      .toLowerCase();
    return (
      (activeTopic === "all" || note.topics.includes(activeTopic)) &&
      haystack.includes(query.trim().toLowerCase())
    );
  });
  const years =
    scope === "archive"
      ? Array.from(
          { length: Number(chronologyCoverage.asOf.slice(0, 4)) - 2009 + 1 },
          (_, index) => String(2009 + index),
        )
      : [...new Set(context.notes.map((note) => note.publishedOn.slice(0, 4)))];
  const year = years.includes(selectedYear) ? selectedYear : "all";
  const filtered = matching.filter(
    (note) => year === "all" || note.publishedOn.startsWith(year),
  );
  const visible = expanded ? filtered : timelineHighlights(filtered);
  const NoteHeading = standalone ? (expanded ? "h3" : "h2") : "h4";
  const YearHeading = standalone ? "h2" : "h3";
  function changeScope(value: "analysis" | "archive") {
    setScope(value);
    setSelectedYear("all");
    setTopic("all");
    setQuery("");
    setExpanded(false);
  }
  function clearFilters() {
    setSelectedYear("all");
    setTopic("all");
    setQuery("");
    setExpanded(false);
  }
  return (
    <section
      className="card report-context"
      data-testid={standalone ? "screen-timeline" : "report-timeline"}
      aria-labelledby="report-context-heading"
    >
      <header className="report-context-heading">
        <div>
          <p className="report-context-eyebrow">From the reports</p>
          {standalone ? (
            <h1 id="report-context-heading">Economic timeline</h1>
          ) : (
            <h2 id="report-context-heading">Historical context</h2>
          )}
          <p className="report-context-intro">
            A source-backed chronology of economic decisions, assessments and
            expectations.
          </p>
        </div>
        <span className="report-context-pilot">Selected report notes</span>
      </header>
      {result && (
        <div
          className="report-context-modes"
          role="group"
          aria-label="Chronology scope"
        >
          <button
            aria-pressed={scope === "analysis"}
            onClick={() => changeScope("analysis")}
          >
            Analysis period
          </button>
          <button
            aria-pressed={scope === "archive"}
            onClick={() => changeScope("archive")}
          >
            Explore chronology
          </button>
        </div>
      )}
      <div className="report-context-scope">
        <span>{reportCountryNames[context.country]}</span>
        <span>
          {scope === "archive"
            ? "All economic topics"
            : context.topics.map((t) => topicNames[t]).join(" + ")}
        </span>
        {context.start && context.end && (
          <span>
            {dateLabel(context.start, true)} – {dateLabel(context.end, true)}
          </span>
        )}
      </div>
      {scope === "archive" && result && (
        <p className="report-context-cutoff" data-testid="report-archive-scope">
          Browsing the full selected chronology, through{" "}
          {dateLabel(chronologyCoverage.asOf, true)}. This view extends beyond
          your analysis sample and is not used by the model.
        </p>
      )}
      {scope === "archive" &&
        chronologyCoverage.byCountry[context.country].missingYears.length >
          0 && (
          <p className="report-context-cutoff" data-testid="chronology-gap">
            No date-verified note is included for{" "}
            {chronologyCoverage.byCountry[context.country].missingYears.join(
              ", ",
            )}
            .
          </p>
        )}
      {context.forecast && !context.message && (
        <p className="report-context-cutoff" data-testid="report-cutoff">
          Publication cutoff at the forecast origin’s period end: {context.end}.
          Later publications are excluded. These notes are not inputs to the
          forecast.
        </p>
      )}
      {context.message ? (
        <p role="status">{context.message}</p>
      ) : (
        <>
          <div className="report-context-filters">
            <label>
              <span>Country / region</span>
              <select
                aria-label="Chronology country"
                value={country}
                onChange={(event) => {
                  setSelectedCountry(event.target.value as ReportCountry);
                  clearFilters();
                }}
              >
                {(scope === "archive" ? reportCountries : available).map(
                  (value) => (
                    <option key={value} value={value}>
                      {reportCountryNames[value]}
                    </option>
                  ),
                )}
              </select>
            </label>
            <label>
              <span>Topic</span>
              <select
                aria-label="Chronology topic"
                value={activeTopic}
                onChange={(event) => {
                  setTopic(event.target.value as ReportTopic | "all");
                  setExpanded(false);
                }}
              >
                <option value="all">
                  {scope === "archive" ? "All topics" : "All selected topics"}
                </option>
                {context.topics.map((value) => (
                  <option key={value} value={value}>
                    {topicNames[value]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Year</span>
              <select
                aria-label="Timeline year"
                value={year}
                onChange={(event) => {
                  setSelectedYear(event.target.value);
                  setExpanded(false);
                }}
              >
                <option value="all">All years</option>
                {years.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="report-context-search">
              <span>Search notes</span>
              <input
                type="search"
                aria-label="Search chronology notes"
                placeholder="Title, institution or quoted words"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setExpanded(false);
                }}
              />
            </label>
          </div>
          <div className="report-context-toolbar">
            <p aria-live="polite" data-testid="timeline-note-count">
              {expanded || visible.length === filtered.length
                ? `${visible.length} ${visible.length === 1 ? "note" : "notes"}`
                : `${visible.length} highlights · ${filtered.length} matching notes`}
            </p>
            {(query || activeTopic !== "all" || year !== "all") && (
              <button className="report-context-reset" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
          {filtered.length === 0 ? (
            <p role="status">
              No selected notes match these variables and dates or filters. This
              does not mean no relevant events occurred.
            </p>
          ) : (
            <ol id="report-context-notes" className="report-context-list">
              {visible.map((note, index) => (
                <Fragment key={note.id}>
                  {expanded &&
                    (index === 0 ||
                      visible[index - 1].publishedOn.slice(0, 4) !==
                        note.publishedOn.slice(0, 4)) && (
                      <li className="report-context-year-label">
                        <YearHeading>
                          {note.publishedOn.slice(0, 4)}
                        </YearHeading>
                      </li>
                    )}
                  <li
                    data-note-id={note.id}
                    data-note-country={note.country}
                    data-note-topics={note.topics.join(" ")}
                  >
                    <time dateTime={note.publishedOn}>
                      {dateLabel(note.publishedOn, true)}
                    </time>
                    <article className="report-context-note">
                      <div className="report-context-meta">
                        <span
                          className={`report-context-institution ${note.source.institution.toLowerCase()}`}
                        >
                          {note.source.institution}
                        </span>
                        <span>{note.kind}</span>
                        {note.actor &&
                          note.actor !== note.source.institution && (
                            <span>{note.actor}</span>
                          )}
                      </div>
                      <NoteHeading>{note.title}</NoteHeading>
                      <p>{note.summary}</p>
                      {note.referencePeriod && (
                        <p className="report-context-reference">
                          Reference period: {note.referencePeriod}
                        </p>
                      )}
                      <details>
                        <summary>View source passage</summary>
                        <p className="report-context-source-meta">
                          Published {dateLabel(note.publishedOn, true)}
                          {note.eventOn &&
                            note.eventOn !== note.publishedOn &&
                            ` · Event ${dateLabel(note.eventOn, true)}`}
                        </p>
                        {(note.source.passages ?? [note.source]).map(
                          (passage, passageIndex) => (
                            <div key={`${passage.chunkId}-${passageIndex}`}>
                              {passage.section && (
                                <p className="report-context-source-meta">
                                  {passage.section}
                                </p>
                              )}
                              <blockquote lang={note.source.language ?? "en"}>
                                {passage.quote}
                              </blockquote>
                              <a
                                href={passage.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {note.source.title}
                                {(note.source.passages?.length ?? 0) > 1
                                  ? ` · Passage ${passageIndex + 1}`
                                  : ""}{" "}
                                ↗
                              </a>
                            </div>
                          ),
                        )}
                        {note.source.publicationEvidenceUrl && (
                          <a
                            className="report-context-date-source"
                            href={note.source.publicationEvidenceUrl}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Publication date source ↗
                          </a>
                        )}
                      </details>
                    </article>
                  </li>
                </Fragment>
              ))}
            </ol>
          )}
          {(expanded || filtered.length > visible.length) && (
            <button
              className="report-context-expand"
              aria-expanded={expanded}
              aria-controls="report-context-notes"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded
                ? "Show highlights"
                : `Show all ${filtered.length} notes`}
            </button>
          )}
        </>
      )}
      <p className="report-context-footnote">
        {reportCountries.length} countries and regions, 2009–2026. Selected
        official-source notes, ordered by publication date; this is not a
        complete event history. Highlights sample distinct reports across the
        period. Forecasts, recommendations and decisions retain their original
        meaning. Summaries are AI-assisted, with original source passages. These
        notes are not model inputs and do not explain or validate your
        estimates.
      </p>
    </section>
  );
}
