import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  AnswerCard,
  ReportModeChoice,
  type ReportAnswer,
} from "../src/components/AskReports";

const answer: ReportAnswer = {
  question: "Could the Fed cut faster?",
  status: "answered",
  retrieved: 4,
  as_of: null,
  engine: "Qwen3.5-9B",
  answer: "This was a conditional ability, rather than a commitment [S1].",
  claims: [
    {
      claim: "",
      source_id: "S1",
      quote: "we have the ability to react to that by, by cutting faster.",
      title: "FOMC press conference — 2024-09-18",
      institution: "Fed",
      speaker: "CHAIR POWELL",
      published_at: null,
      event_date: "2024-09-18",
      pages: [12],
      url: "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20240918.pdf#page=12",
    },
  ],
  missing_institutions: [],
};

describe("local report chat answers", () => {
  it("offers separate accessible report and archive choices", () => {
    const markup = renderToStaticMarkup(
      <ReportModeChoice mode="document" disabled={false} onChange={() => {}} />,
    );
    expect(markup).toContain("Ask a report");
    expect(markup).toContain("Search the archive");
    expect(markup.match(/type="radio"/g)).toHaveLength(2);
    expect(markup).toMatch(
      /<input(?=[^>]*value="document")(?=[^>]*checked)[^>]*>/,
    );
  });

  it("shows the selected report, coverage and regional source scope", () => {
    const markup = renderToStaticMarkup(
      <AnswerCard
        answer={{
          ...answer,
          mode: "document",
          report_title: "Beige Book",
          coverage: {
            kind: "prepared_report_text",
            total_passages: 15,
            read_passages: 15,
            parts: 2,
            complete: true,
            aggregation: "synthesised",
          },
          claims: [
            { ...answer.claims[0], section: "St. Louis", region: "St. Louis" },
          ],
        }}
      />,
    );
    expect(markup).toContain("Ask a report · Beige Book");
    expect(markup).toContain("15 of 15 prepared passages read");
    expect(markup).toContain("Region: St. Louis");
  });
  it("links answer references to exact quotations and preserves source attribution", () => {
    const markup = renderToStaticMarkup(<AnswerCard answer={answer} />);
    expect(markup).toContain("conditional ability, rather than a commitment");
    const target = markup.match(/href="#([^"]+-S1)"/);
    expect(target).not.toBeNull();
    expect(markup).toContain(`id="${target![1]}"`);
    expect(markup).toContain(answer.claims[0].quote);
    expect(markup).toContain("CHAIR POWELL");
    expect(markup).toContain("Publication date unverified");
    expect(markup).toContain("Qwen3.5-9B");
  });

  it("retains the older cited-claim format and does not render model text as HTML", () => {
    const markup = renderToStaticMarkup(
      <AnswerCard
        answer={{
          ...answer,
          answer: undefined,
          claims: [
            { ...answer.claims[0], claim: "<script>untrusted</script>" },
          ],
        }}
      />,
    );
    expect(markup).toContain("&lt;script&gt;");
    expect(markup).not.toContain("<script>");
    expect(markup).toContain(answer.claims[0].quote);
  });

  it("shows insufficient evidence without presenting an unsupported generated answer", () => {
    const markup = renderToStaticMarkup(
      <AnswerCard
        answer={{
          ...answer,
          status: "insufficient_evidence",
          answer: "An unsupported claim",
          claims: [],
        }}
      />,
    );
    expect(markup).toContain("No supported answer was produced");
    expect(markup).not.toContain("An unsupported claim");
  });
});
