import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import "./ask-reports.css";

const reportTypes = [
  ["statement", "Fed", "FOMC statement"],
  ["minutes", "Fed", "FOMC minutes"],
  ["press_conference", "Fed", "FOMC press conference"],
  ["beige_book", "Fed", "Beige Book"],
  ["sloos", "Fed", "Senior Loan Officer Survey"],
  ["outlook", "OECD", "Economic Outlook"],
  ["interim_report", "OECD", "Interim Economic Outlook"],
] as const;
const months = Array.from({ length: 12 }, (_, index) =>
  new Intl.DateTimeFormat("en", { month: "long", timeZone: "UTC" }).format(
    new Date(Date.UTC(2024, index, 1)),
  ),
);

const emptyFilters = {
  institution: "",
  kind: "",
  year: "",
  month: "",
  as_of: "",
};
const examples = [
  {
    label: "Powell’s policy options",
    documentId: "fed-press_conference-20240918",
    question:
      "At his September 18, 2024 press conference, what did Powell say the Fed could do if the labor market slowed unexpectedly? Was this a commitment?",
    filters: {
      institution: "Fed",
      kind: "press_conference",
      year: "2024",
      month: "9",
      as_of: "",
    },
  },
  {
    label: "Bank lending conditions",
    documentId: "fed-sloos-2024-07",
    question:
      "What did the July 2024 SLOOS say about domestic C&I lending standards and demand?",
    filters: {
      ...emptyFilters,
      institution: "Fed",
      kind: "sloos",
      year: "2024",
      month: "8",
    },
  },
  {
    label: "OECD US growth outlook",
    documentId: "10.1787/ae8c39ec-en",
    question:
      "What US GDP growth did the September 2022 OECD Interim Economic Outlook project for 2023?",
    filters: {
      ...emptyFilters,
      institution: "OECD",
      kind: "interim_report",
      year: "2022",
      month: "9",
    },
  },
];

interface Claim {
  claim: string;
  quote: string;
  title: string;
  institution: string;
  published_at: string | null;
  event_date: string | null;
  pages: number[];
  url: string;
  source_id?: string;
  speaker?: string | null;
  section?: string | null;
  region?: string | null;
}
type ReportMode = "document" | "archive";
interface ReportRecord {
  id: string;
  title: string;
  institution: string;
  kind: string;
  published_at: string | null;
  publication_verified: boolean;
  event_date: string | null;
  filter_date: string | null;
  passages: number;
  url: string;
}
export interface ReportAnswer {
  question: string;
  status: "answered" | "insufficient_evidence";
  retrieved: number;
  as_of: string | null;
  claims: Claim[];
  missing_institutions: string[];
  answer?: string;
  engine?: string;
  elapsed_seconds?: number;
  mode?: ReportMode;
  report_title?: string | null;
  coverage?: {
    kind: "prepared_report_text" | "retrieved_passages";
    read_passages: number;
    total_passages: number;
    parts: number;
    complete: boolean;
    aggregation: string;
  };
}

export function ReportModeChoice({
  mode,
  disabled,
  onChange,
}: {
  mode: ReportMode;
  disabled: boolean;
  onChange: (mode: ReportMode) => void;
}) {
  const name = useId();
  return (
    <fieldset className="reports-mode-choice" disabled={disabled}>
      <legend className="sr-only">How would you like to ask?</legend>
      {(
        [
          [
            "document",
            "Ask a report",
            "Choose a report and read its prepared text.",
          ],
          [
            "archive",
            "Search the archive",
            "Find relevant passages across Fed and OECD reports.",
          ],
        ] as const
      ).map(([value, label, description]) => (
        <label key={value} className={mode === value ? "is-selected" : ""}>
          <input
            type="radio"
            name={name}
            value={value}
            checked={mode === value}
            onChange={() => onChange(value)}
          />
          <span>
            <strong>{label}</strong>
            <span className="small muted">{description}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}

export function AnswerCard({ answer }: { answer: ReportAnswer }) {
  const citationPrefix = useId();
  const sourceIds = new Set(answer.claims.map((source) => source.source_id));
  return (
    <article className="card stack reports-answer">
      <div className="stack reports-answer-heading">
        <span className="overline">Question</span>
        <h2>{answer.question}</h2>
        {answer.mode && (
          <p className="small">
            {answer.mode === "document"
              ? `Ask a report · ${answer.report_title ?? "Selected report"}`
              : "Search the archive"}
          </p>
        )}
        <p className="small muted">
          {answer.retrieved} {answer.retrieved === 1 ? "passage" : "passages"}{" "}
          reviewed{answer.as_of ? ` · Published by ${answer.as_of}` : ""}
          {answer.engine ? ` · ${answer.engine}` : ""}
          {answer.elapsed_seconds !== undefined
            ? ` · ${Math.round(answer.elapsed_seconds)}s`
            : ""}
        </p>
        {answer.coverage && (
          <p className="small muted">
            {answer.coverage.kind === "prepared_report_text"
              ? `${answer.coverage.read_passages} of ${answer.coverage.total_passages} prepared passages read`
              : `${answer.coverage.read_passages} retrieved passages read`}
            {` · ${answer.coverage.parts} ${answer.coverage.parts === 1 ? "part" : "parts"}`}
            {!answer.coverage.complete && " · Incomplete coverage"}
          </p>
        )}
      </div>
      {answer.status === "insufficient_evidence" ? (
        <p>
          No supported answer was produced from the selected passages for this
          question.
        </p>
      ) : (
        <>
          {answer.answer && (
            <div
              className="reports-prose"
              role="region"
              aria-label="Sourced answer"
            >
              {answer.answer.split(/\n\s*\n/).map((paragraph, index) => (
                <p key={index}>
                  {paragraph.split(/(\[S\d+\])/).map((part, partIndex) => {
                    const id = part.slice(1, -1);
                    return /^\[S\d+\]$/.test(part) && sourceIds.has(id) ? (
                      <a
                        className="reports-citation"
                        key={partIndex}
                        href={`#${citationPrefix}-${id}`}
                        aria-label={`Read source ${id}`}
                      >
                        {part}
                      </a>
                    ) : (
                      part
                    );
                  })}
                </p>
              ))}
            </div>
          )}
          {answer.answer && <h3 className="reports-source-heading">Sources</h3>}
          {answer.claims.map((source, index) => (
            <div className="reports-claim" key={index}>
              {source.claim && <p>{source.claim}</p>}
              <figure
                id={
                  source.source_id
                    ? `${citationPrefix}-${source.source_id}`
                    : undefined
                }
              >
                <blockquote>{source.quote}</blockquote>
                <figcaption className="small">
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.source_id ? `${source.source_id} · ` : ""}
                    {source.title}
                    {source.pages.length > 0 &&
                      ` · PDF ${source.pages.length === 1 ? "p." : "pp."} ${source.pages.join(", ")}`}
                  </a>
                  <span className="muted">
                    {source.institution}
                    {source.speaker ? ` · ${source.speaker}` : ""} ·{" "}
                    {source.published_at
                      ? `Published ${source.published_at.slice(0, 10)}`
                      : `${source.event_date ? `Event ${source.event_date} · ` : ""}Publication date unverified`}
                  </span>
                  {(source.region || source.section) && (
                    <span className="muted">
                      {source.region ? `Region: ${source.region} · ` : ""}
                      {source.section}
                    </span>
                  )}
                </figcaption>
              </figure>
            </div>
          ))}
          {answer.missing_institutions.map((name) => (
            <p key={name} className="small muted">
              No supported answer was produced from the {name} passages for that
              part of the question.
            </p>
          ))}
        </>
      )}
    </article>
  );
}

export default function AskReports({ endpoint }: { endpoint: string }) {
  const [mode, setMode] = useState<ReportMode>("document");
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [reportId, setReportId] = useState("");
  const [reportSearch, setReportSearch] = useState("");
  const [catalogueLoading, setCatalogueLoading] = useState(true);
  const [catalogueError, setCatalogueError] = useState("");
  const [catalogueRetry, setCatalogueRetry] = useState(0);
  const [question, setQuestion] = useState("");
  const [filters, setFilters] = useState(emptyFilters);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [answers, setAnswers] = useState<ReportAnswer[]>([]);
  const questionInput = useRef<HTMLTextAreaElement>(null);
  const cleanedQuestion = question.trim().replace(/\s+/g, " ");
  useEffect(() => {
    if (!endpoint) return;
    const controller = new AbortController();
    fetch(endpoint.replace(/\/ask$/, "/reports"), { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok || !Array.isArray(body.reports)) {
          throw new Error("The report list is unavailable.");
        }
        setReports(body.reports);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setCatalogueError(
            error instanceof Error
              ? error.message
              : "The report list is unavailable.",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogueLoading(false);
      });
    return () => controller.abort();
  }, [endpoint, catalogueRetry]);
  const availableReports = reports.filter((report) => {
    const date = report.filter_date ?? "";
    return (
      (!filters.institution || report.institution === filters.institution) &&
      (!filters.kind || report.kind === filters.kind) &&
      (!filters.year || date.slice(0, 4) === filters.year) &&
      (!filters.month || Number(date.slice(5, 7)) === Number(filters.month)) &&
      (!filters.as_of ||
        (report.publication_verified &&
          !!report.published_at &&
          report.published_at.slice(0, 10) <= filters.as_of)) &&
      (!reportSearch ||
        `${report.title} ${report.id} ${report.institution}`
          .toLowerCase()
          .includes(reportSearch.toLowerCase()))
    );
  });
  const selectedReport = availableReports.find(
    (report) => report.id === reportId,
  );
  const selectedType = reportTypes.find(([key]) => key === filters.kind);
  const activeFilters = [
    filters.institution,
    selectedType?.[2],
    [filters.month && months[Number(filters.month) - 1], filters.year]
      .filter(Boolean)
      .join(" "),
    filters.as_of && `Published by ${filters.as_of}`,
  ].filter(Boolean);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      pending ||
      cleanedQuestion.length < 4 ||
      (mode === "document" && !selectedReport)
    )
      return;
    setPending(true);
    setError("");
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: cleanedQuestion,
          mode,
          ...(mode === "document" ? { document_id: reportId } : {}),
          institution: filters.institution || null,
          kind: filters.kind || null,
          year: filters.year ? Number(filters.year) : null,
          month: filters.month ? Number(filters.month) : null,
          as_of: filters.as_of || null,
        }),
      });
      const result: ReportAnswer & { error?: string } = await response.json();
      if (!response.ok || !Array.isArray(result.claims)) {
        setError(
          result.error || "The report service couldn’t complete the question.",
        );
        return;
      }
      setAnswers((current) => [result, ...current]);
    } catch {
      setError(
        "The report service is unavailable. Check the local preview and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="reports-screen" aria-labelledby="reports-heading">
      <div className="page-heading">
        <div className="row">
          <span className="overline">Research archive</span>
          {endpoint && <span className="badge draft">Local preview</span>}
        </div>
        <h1 id="reports-heading">Ask the reports</h1>
        <p>
          Ask a question about Fed and OECD publications from 2009 to 2026.
          Explore answers with original quotations and links to the reports.
        </p>
        <p className="small muted">
          Answers are in English. Choose one report or search the archive. Each
          question is independent.
        </p>
      </div>
      {endpoint ? (
        <>
          <form className="card stack reports-form" onSubmit={ask}>
            <ReportModeChoice
              mode={mode}
              disabled={pending}
              onChange={setMode}
            />
            {mode === "document" && (
              <div className="stack reports-document-picker">
                <label className="field">
                  Find a report
                  <input
                    type="search"
                    value={reportSearch}
                    onChange={(event) => setReportSearch(event.target.value)}
                    placeholder="Title, institution or date"
                    disabled={pending}
                  />
                </label>
                <label className="field">
                  Choose a report
                  <select
                    value={selectedReport ? reportId : ""}
                    onChange={(event) => setReportId(event.target.value)}
                    required
                    disabled={pending || catalogueLoading}
                  >
                    <option value="">
                      {catalogueLoading
                        ? "Loading reports…"
                        : "Select a report"}
                    </option>
                    {availableReports.map((report) => (
                      <option key={report.id} value={report.id}>
                        {report.institution} · {report.title}
                      </option>
                    ))}
                  </select>
                </label>
                {catalogueError ? (
                  <p role="alert">
                    {catalogueError}{" "}
                    <button
                      type="button"
                      onClick={() => {
                        setCatalogueLoading(true);
                        setCatalogueError("");
                        setCatalogueRetry((n) => n + 1);
                      }}
                    >
                      Retry report list
                    </button>
                  </p>
                ) : (
                  <p className="small muted">
                    {availableReports.length}{" "}
                    {availableReports.length === 1
                      ? "report matches"
                      : "reports match"}{" "}
                    your filters.
                    {selectedReport &&
                      ` ${selectedReport.passages} prepared passages in this report.`}
                  </p>
                )}
                <p className="small muted">
                  Reads the selected report’s prepared text. Figures and
                  image-only tables are excluded. Long reports are read in parts
                  and can take several minutes.
                </p>
              </div>
            )}
            <label className="field">
              <span>Your question</span>
              <textarea
                ref={questionInput}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="What did the Fed say about inflation risks?"
                required
                maxLength={800}
                rows={3}
              />
            </label>
            <div
              className="row reports-examples"
              role="group"
              aria-label="Example questions"
            >
              <span className="small muted">Try an example</span>
              {examples.map((example) => (
                <button
                  key={example.label}
                  type="button"
                  onClick={() => {
                    setQuestion(example.question);
                    setFilters(example.filters);
                    setReportId(example.documentId);
                    setReportSearch("");
                    questionInput.current?.focus();
                  }}
                >
                  {example.label}
                </button>
              ))}
            </div>
            <details className="reports-filters">
              <summary>
                Report filters
                {activeFilters.length > 0 && (
                  <span className="small muted">
                    {activeFilters.join(" · ")}
                  </span>
                )}
              </summary>
              <div className="reports-filter-grid">
                <label className="field">
                  Institution
                  <select
                    value={filters.institution}
                    onChange={(event) => {
                      const institution = event.target.value;
                      setFilters({
                        ...filters,
                        institution,
                        kind:
                          institution && selectedType?.[1] !== institution
                            ? ""
                            : filters.kind,
                      });
                    }}
                  >
                    <option value="">Fed and OECD</option>
                    <option value="Fed">Federal Reserve</option>
                    <option value="OECD">OECD</option>
                  </select>
                </label>
                <label className="field">
                  Report type
                  <select
                    value={filters.kind}
                    onChange={(event) =>
                      setFilters({ ...filters, kind: event.target.value })
                    }
                  >
                    <option value="">All reports</option>
                    {reportTypes
                      .filter(
                        ([, institution]) =>
                          !filters.institution ||
                          institution === filters.institution,
                      )
                      .map(([key, , label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="field">
                  Document year
                  <input
                    type="number"
                    min={2009}
                    max={2026}
                    placeholder="Any year"
                    value={filters.year}
                    onChange={(event) => {
                      const year = event.target.value;
                      setFilters({
                        ...filters,
                        year,
                        month: year ? filters.month : "",
                      });
                    }}
                  />
                </label>
                <label className="field">
                  Document month
                  <select
                    disabled={!filters.year}
                    value={filters.month}
                    onChange={(event) =>
                      setFilters({ ...filters, month: event.target.value })
                    }
                  >
                    <option value="">Any month</option>
                    {months.map((month, index) => (
                      <option key={month} value={index + 1}>
                        {month}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Published by
                  <input
                    type="date"
                    min="2009-01-01"
                    max="2026-11-07"
                    value={filters.as_of}
                    aria-describedby="reports-filter-help"
                    onChange={(event) =>
                      setFilters({ ...filters, as_of: event.target.value })
                    }
                  />
                </label>
              </div>
              <p id="reports-filter-help" className="small muted">
                Year and month use the confirmed publication date when available
                and the report or event period otherwise. Published by includes
                only documents confirmed public by the end of that day in New
                York.
              </p>
            </details>
            <div className="row reports-submit">
              <button
                className="primary"
                type="submit"
                disabled={
                  pending ||
                  cleanedQuestion.length < 4 ||
                  (mode === "document" && !selectedReport)
                }
              >
                {mode === "document" ? "Ask this report" : "Search and answer"}
              </button>
              <span role="status" className="small muted">
                {pending
                  ? mode === "document"
                    ? "Reading the selected report and writing a sourced answer. This can take several minutes…"
                    : "Searching the archive and reading relevant passages. This can take a few minutes…"
                  : !error && answers.length > 0
                    ? "Response ready below."
                    : ""}
              </span>
            </div>
            {error && <p role="alert">{error}</p>}
          </form>
          {answers.length > 0 && (
            <section
              className="stack reports-answers"
              aria-label="Report answers"
            >
              {answers.map((answer, index) => (
                <AnswerCard key={answers.length - index} answer={answer} />
              ))}
            </section>
          )}
        </>
      ) : (
        <p className="card">The report service is unavailable in this build.</p>
      )}
    </section>
  );
}
