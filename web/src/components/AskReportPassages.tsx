import { useEffect, useRef, useState } from "react";
import manifest from "../data/report-search/manifest.json";
import { ReportEvidenceClient } from "../reportEvidenceClient";
import {
  experimentalContextSentence,
  type EvidenceAnswer,
  type EvidenceFilters,
  type EvidenceHit,
} from "../reportSearch";
import "./ask-report-passages.css";

const kindNames: Record<string, string> = {
  statement: "FOMC statement",
  minutes: "FOMC minutes",
  beige_book: "Beige Book",
  sloos: "Senior Loan Officer Survey",
  outlook: "Economic Outlook",
  interim_report: "Interim Economic Outlook",
  policy_release: "Policy release",
};
const countryName = (id: string) =>
  manifest.countries.find((c) => c.id === id)?.name ?? id;
const examples = [
  "What target range did the March 20, 2024 FOMC statement maintain, and what confidence was needed before reducing it?",
  "What did the OECD say about inflation in Germany and France in 2022?",
  "What did the SLOOS published in August 2024 say about lending standards?",
];
function SourcePassages({
  passages,
  related = false,
  comparison = false,
}: {
  passages: EvidenceHit[];
  related?: boolean;
  comparison?: boolean;
}) {
  return (
    <ol className="evidence-results">
      {passages.map((p, i) => (
        <li
          key={p.id}
          data-evidence-id={related || comparison ? undefined : p.id}
          data-comparison-id={comparison ? p.id : undefined}
          data-related-id={related ? p.id : undefined}
          data-evidence-country={p.country}
        >
          <article className="evidence-card">
            <div className="evidence-meta">
              <span>
                {related ? "Related source" : "Source"} {i + 1}
              </span>
              <span>{p.institution}</span>
              <span>{countryName(p.country)}</span>
              <span>{kindNames[p.kind] ?? p.kind}</span>
            </div>
            <h3>
              <a href={p.url} target="_blank" rel="noreferrer">
                {p.title} ↗
              </a>
            </h3>
            {p.verifiedEventOn && (
              <p className="evidence-meeting">
                <strong>
                  Meeting / event{" "}
                  <time dateTime={p.verifiedEventOn}>{p.verifiedEventOn}</time>
                </strong>
              </p>
            )}
            <p className="evidence-dates">
              Published <time dateTime={p.publishedOn}>{p.publishedOn}</time>
            </p>
            {p.section && (
              <p className="evidence-section">
                {p.section}
                {p.region ? ` · Regional evidence: ${p.region}` : ""}
              </p>
            )}
            {p.speaker && (
              <p className="evidence-section">Speaker: {p.speaker}</p>
            )}
            <blockquote>{p.text}</blockquote>
            <a
              className="evidence-original"
              href={p.url}
              target="_blank"
              rel="noreferrer"
            >
              Open official source ↗
            </a>
          </article>
        </li>
      ))}
    </ol>
  );
}
export function EvidenceAnswerCard({ answer }: { answer: EvidenceAnswer }) {
  const period = answer.plan.period;
  return (
    <section
      className="evidence-answer"
      aria-labelledby="evidence-answer-title"
      data-testid="evidence-answer"
      data-status={answer.status}
    >
      <header className="evidence-answer-heading">
        <p className="overline">Original source passages</p>
        <h2 id="evidence-answer-title">
          {answer.status === "comparison"
            ? "Decisions in chronological order"
            : answer.status === "not_found"
              ? "Not found in these reports"
              : answer.status === "partial"
                ? "Evidence found for only part of your question"
                : "Passages relevant to your question"}
        </h2>
        <p>
          {answer.status === "not_found"
            ? "No supporting passage was found in this indexed selection. This does not mean the event did not occur."
            : "These are quotations, not a generated answer. Read each passage with its date, country and source scope."}
        </p>
        <div className="evidence-period" data-testid="evidence-period">
          {answer.status !== "comparison" &&
            Object.entries(period.resolvedMeetings).map(([bank, date]) => (
              <p key={bank}>
                <strong>
                  {bank} ·{" "}
                  {period.relative === "previous" ? "Previous" : "Latest"}{" "}
                  meeting represented in this corpus: {date}
                </strong>
              </p>
            ))}
          {(period.event.date ||
            period.event.month ||
            period.event.years.length > 0) && (
            <p>
              <strong>
                Requested meeting / event:{" "}
                {period.event.date ??
                  period.event.month ??
                  period.event.years.join(", ")}
              </strong>
            </p>
          )}
          {(period.publication.date ||
            period.publication.month ||
            period.publication.years.length > 0) && (
            <p>
              Requested publication:{" "}
              {period.publication.date ??
                period.publication.month ??
                period.publication.years.join(", ")}
            </p>
          )}
          <p>
            Corpus reviewed through {period.asOf}. Meeting dates and publication
            dates are separate.
          </p>
          {period.unresolved && <p>{period.unresolved}</p>}
        </div>
        {answer.missingCountries.length > 0 && (
          <p data-testid="evidence-missing">
            No matching evidence for:{" "}
            {answer.missingCountries.map(countryName).join(", ")}.
          </p>
        )}
      </header>
      {answer.status === "comparison" && (
        <section data-testid="comparison-evidence">
          <p lang="tr">
            Bu soru birden fazla kararın karşılaştırılmasını gerektiriyor;
            ilgili kararlar tarih sırasıyla aşağıda.
          </p>
          <p>
            This question requires comparing multiple decisions. Relevant source
            passages are listed chronologically. This selection is not a
            complete decision history; no first, last, highest, lowest or count
            is asserted.
          </p>
          <SourcePassages
            passages={answer.comparisonPassages ?? []}
            comparison
          />
        </section>
      )}
      <SourcePassages passages={answer.passages} />
      {answer.relatedPassages.length > 0 && (
        <section className="evidence-related" data-testid="related-evidence">
          <h3>Related, but not an answer</h3>
          <p>
            These passages do not establish the main elements or factual premise
            of your question. They are shown separately as context.
          </p>
          <SourcePassages passages={answer.relatedPassages} related />
        </section>
      )}
    </section>
  );
}
export default function AskReportPassages() {
  const [question, setQuestion] = useState("");
  const [filters, setFilters] = useState<EvidenceFilters>({});
  const [answer, setAnswer] = useState<EvidenceAnswer | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [contextEnabled, setContextEnabled] = useState(false);
  const [context, setContext] = useState<string | null>(null);
  const [contextError, setContextError] = useState("");
  const [client] = useState(() => new ReportEvidenceClient());
  const request = useRef(0);
  const contextPath: string = import.meta.env.MACROLAB_CONTEXT_TEST_PATH;
  useEffect(() => () => client.dispose(), [client]);
  useEffect(() => {
    if (!answer || !contextEnabled || !contextPath) return;
    const controller = new AbortController();
    void experimentalContextSentence(
      answer,
      true,
      contextPath,
      controller.signal,
    )
      .then(setContext)
      .catch((e: unknown) => {
        if (!controller.signal.aborted)
          setContextError(e instanceof Error ? e.message : String(e));
      });
    return () => controller.abort();
  }, [answer, contextEnabled, contextPath]);
  async function ask() {
    const cleaned = question.trim();
    if (!cleaned || pending) return;
    const id = ++request.current;
    setPending(true);
    setError("");
    setContextError("");
    setAnswer(null);
    setContext(null);
    try {
      const result = await client.search(cleaned, filters);
      if (id === request.current) {
        setAnswer(result);
        window.dispatchEvent(
          new CustomEvent("macrolab-evidence-ready", {
            detail: { question: cleaned, answer: result },
          }),
        );
      }
    } catch (e: unknown) {
      if (id === request.current)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === request.current) setPending(false);
    }
  }
  return (
    <section
      className="evidence-screen"
      data-testid="screen-reports"
      aria-labelledby="ask-evidence-heading"
    >
      <header className="evidence-page-heading">
        <p className="overline">Explore the evidence</p>
        <h1 id="ask-evidence-heading">Ask the reports</h1>
        <p>
          Find original passages in economic reports. Every result includes its
          source, publication date and country.
        </p>
      </header>
      <form
        className="card evidence-form"
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
      >
        <label className="evidence-question">
          <span>Your question</span>
          <textarea
            aria-label="Your question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={1500}
            rows={3}
            placeholder="Ask in English, and include a country, topic and period…"
            required
          />
        </label>
        <div className="evidence-examples" aria-label="Example questions">
          {examples.map((example, i) => (
            <button
              type="button"
              key={example}
              onClick={() => {
                setQuestion(example);
                setFilters({});
              }}
            >
              {
                [
                  "Fed policy decision",
                  "Compare inflation reports",
                  "Bank lending conditions",
                ][i]
              }
            </button>
          ))}
        </div>
        <details className="evidence-filters">
          <summary>Refine sources</summary>
          <div className="evidence-filter-grid">
            <label>
              <span>Country / region</span>
              <select
                aria-label="Evidence country"
                value={filters.countries?.[0] ?? ""}
                onChange={(e) =>
                  setFilters({
                    ...filters,
                    countries: e.target.value ? [e.target.value] : [],
                  })
                }
              >
                <option value="">From your question</option>
                {manifest.countries.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Institution</span>
              <select
                aria-label="Evidence institution"
                value={filters.institution ?? ""}
                onChange={(e) =>
                  setFilters({ ...filters, institution: e.target.value })
                }
              >
                <option value="">From your question</option>
                {manifest.institutions.map((id) => (
                  <option key={id}>{id}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Report type</span>
              <select
                aria-label="Evidence report type"
                value={filters.kind ?? ""}
                onChange={(e) =>
                  setFilters({ ...filters, kind: e.target.value })
                }
              >
                <option value="">From your question</option>
                {Object.entries(kindNames).map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Year</span>
              <select
                aria-label="Evidence year"
                value={filters.year ?? ""}
                onChange={(e) =>
                  setFilters({ ...filters, year: e.target.value })
                }
              >
                <option value="">From your question</option>
                {Array.from({ length: 18 }, (_, i) => String(2009 + i)).map(
                  (year) => (
                    <option key={year}>{year}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              <span>Published by</span>
              <input
                aria-label="Evidence published by"
                type="date"
                value={filters.publishedBy ?? ""}
                onChange={(e) =>
                  setFilters({ ...filters, publishedBy: e.target.value })
                }
              />
            </label>
          </div>
          <p className="small muted">
            Dates follow stated publication dates. Historical versions have not
            been independently reconstructed. Clear a filter to use the country
            and period in your question.
          </p>
        </details>
        {import.meta.env.DEV && (
          <details className="evidence-experiment">
            <summary>Experimental context sentence · testing only</summary>
            <label>
              <input
                type="checkbox"
                checked={contextEnabled}
                disabled={!contextPath}
                onChange={(e) => {
                  setContextEnabled(e.target.checked);
                  setContext(null);
                  setContextError("");
                }}
              />{" "}
              Enable a short linking sentence
            </label>
            <p className="small muted">
              {contextPath
                ? "Off by default. A test model may select a navigation sentence; economic commentary and rewritten quotations are rejected."
                : "No test model is connected. Source search works without one."}
            </p>
          </details>
        )}
        <div className="evidence-submit">
          <button
            className="primary"
            type="submit"
            disabled={pending || !question.trim()}
          >
            {pending ? "Finding source passages…" : "Find evidence"}
          </button>
          {pending && (
            <button
              type="button"
              onClick={() => {
                request.current++;
                client.dispose();
                setPending(false);
              }}
            >
              Cancel
            </button>
          )}
          <span className="small muted">
            Quotes and sources · No generated economic answer
          </span>
        </div>
      </form>
      <div
        aria-live="polite"
        aria-atomic="true"
        className="small evidence-status"
        data-testid="evidence-status"
      >
        {pending
          ? "Searching the selected reports."
          : answer
            ? `${answer.passages.length + (answer.comparisonPassages?.length ?? 0)} source passages shown.`
            : ""}
      </div>
      {error && (
        <p role="alert" className="card">
          {error}
        </p>
      )}
      {context && (
        <p className="card" data-testid="experimental-context">
          {context}
        </p>
      )}
      {contextError && (
        <p className="small" role="status">
          {contextError}
        </p>
      )}
      {answer && <EvidenceAnswerCard answer={answer} />}
      <details className="evidence-coverage">
        <summary>Which reports are included?</summary>
        <p>
          {manifest.timelineNotes} selected timeline notes across 39 economies,
          plus {manifest.reportDocuments} date-verified Fed statements, minutes,
          Beige Book summaries and Senior Loan Officer Survey reports. Coverage:
          2009–2026; reviewed through {manifest.asOf}.
        </p>
        <p>
          This is a selected archive. Full OECD country reports, unverified
          publication dates, press-conference transcripts and graphical tables
          are not searched. A missing result is a coverage or retrieval limit,
          not proof that an event did not happen.
        </p>
      </details>
    </section>
  );
}
