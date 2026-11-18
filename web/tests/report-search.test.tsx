import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  EvidenceIndex,
  allowedContextSentences,
  experimentalContextSentence,
  planEvidenceSearch,
  searchTokens,
  type EvidenceAnswer,
  type EvidencePassage,
} from "../src/reportSearch";
import { EvidenceAnswerCard } from "../src/components/AskReportPassages";
import manifest from "../src/data/report-search/manifest.json";

function passage(
  id: string,
  text: string,
  change: Partial<EvidencePassage> = {},
): EvidencePassage {
  return {
    id,
    text,
    sourceIds: [id],
    noteIds: [],
    country: "USA",
    institution: "Fed",
    title: "FOMC statement",
    kind: "statement",
    publishedOn: "2024-03-20",
    eventOn: "2024-03-20",
    url: "https://www.federalreserve.gov/monetarypolicy.htm",
    section: "Policy statement",
    speaker: null,
    region: null,
    scope: "report_context",
    sourceType: "report",
    discovery: "",
    ...change,
  };
}
afterEach(() => vi.restoreAllMocks());
describe("extractive report evidence", () => {
  it("keeps related adopted-decision paragraphs rather than replacing the adopted range with later discussion", () => {
    const index = new EvidenceIndex();
    const one = passage(
      "fed:fed-statement-20240320:v1:00001",
      "The Committee decided to maintain the target range. Inflation remains elevated.",
    );
    one.sourceIds = ["fed-statement-20240320:v1:00001"];
    const two = passage(
      "fed:fed-statement-20240320:v1:00002",
      "Treasury purchases will continue over coming months.",
    );
    two.sourceIds = ["fed-statement-20240320:v1:00002"];
    index.add([
      one,
      two,
      passage(
        "discussion",
        "Treasury purchases and future policy purchases were discussed at length.",
        { kind: "minutes" },
      ),
    ]);
    const answer = index.search(
      "What target range and Treasury purchases did the FOMC announce on March 20, 2024?",
    );
    expect(answer.passages.slice(0, 2).map((p) => p.id)).toEqual([
      one.id,
      two.id,
    ]);
  });
  it("keeps earlier/smaller and ability/commitment separate in lexical processing", () => {
    expect(searchTokens("earlier")).not.toEqual(searchTokens("smaller"));
    expect(searchTokens("could")).not.toEqual(searchTokens("will"));
    expect(searchTokens("Treasury")).not.toEqual(searchTokens("agency MBS"));
  });
  it("distinguishes a date cutoff from the word before later in the question", () => {
    const decision = planEvidenceSearch(
      "At the July 31, 2024 FOMC meeting, what confidence was needed before a rate reduction?",
    );
    expect(decision.date).toBe("2024-07-31");
    expect(decision.before).toBe(false);
    expect(decision.years).toEqual(["2024"]);
    const cutoff = planEvidenceSearch(
      "What inflation evidence was published before July 31, 2024?",
    );
    expect(cutoff.before).toBe(true);
    expect(cutoff.dateField).toBe("publication");
  });
  it("uses publication dates for a publication question and preserves meeting dates separately", () => {
    const index = new EvidenceIndex();
    index.add([
      passage("minutes", "Inflation was expected to decline.", {
        kind: "minutes",
        publishedOn: "2024-04-10",
      }),
    ]);
    expect(
      index.search("FOMC minutes published in March 2024 about inflation")
        .status,
    ).toBe("not_found");
    expect(
      index.search(
        "FOMC minutes for the March 20, 2024 meeting about inflation",
      ).passages[0].publishedOn,
    ).toBe("2024-04-10");
  });
  it("returns exact source strings and metadata, with no economic prose generated", () => {
    const p = passage(
      "conditional",
      "We could cut earlier if conditions deteriorated; this is not a commitment.",
    );
    const index = new EvidenceIndex();
    index.add([p]);
    const answer = index.search("Could the FOMC cut earlier in March 2024?");
    expect(answer.passages[0].text).toBe(p.text);
    expect(answer.passages[0].url).toBe(p.url);
    expect(answer.passages[0].publishedOn).toBe(p.publishedOn);
    const html = renderToStaticMarkup(<EvidenceAnswerCard answer={answer} />);
    expect(html).toContain(p.text);
    expect(html).toContain("Published");
    expect(html).not.toContain("will cut");
  });
  it("does not call a one-country result a complete comparison", () => {
    const index = new EvidenceIndex();
    index.add([
      passage("can", "Inflation is projected to decline.", {
        country: "CAN",
        institution: "OECD",
        kind: "outlook",
      }),
    ]);
    const result = index.search(
      "Compare OECD inflation in Canada and Japan in 2024",
    );
    expect(result.status).toBe("partial");
    expect(result.missingCountries).toEqual(["JPN"]);
  });
  it("refuses unsupported country and future-period queries instead of returning a nearby country/year", () => {
    const index = new EvidenceIndex();
    index.add([passage("p", "Inflation remained elevated.")]);
    expect(
      index.search("What inflation did Brazil report in 2024?").passages,
    ).toEqual([]);
    expect(
      index.search("What did the FOMC decide in 2029 about inflation?")
        .passages,
    ).toEqual([]);
    expect(
      renderToStaticMarkup(
        <EvidenceAnswerCard
          answer={index.search("Brazil inflation in 2024")}
        />,
      ),
    ).toContain("Not found in these reports");
  });
  it("separates regional evidence from national sources and escapes source HTML", () => {
    const index = new EvidenceIndex();
    const quote = "Regional inflation <script>alert(1)</script>";
    index.add([
      passage("regional", quote, {
        region: "St. Louis",
        section: "St. Louis",
        kind: "beige_book",
      }),
    ]);
    const html = renderToStaticMarkup(
      <EvidenceAnswerCard answer={index.search("Fed inflation in 2024")} />,
    );
    expect(html).toContain("Regional evidence: St. Louis");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
  it("does not send any model request while the optional context switch is off", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const index = new EvidenceIndex();
    index.add([passage("p", "Inflation remains elevated.")]);
    expect(
      await experimentalContextSentence(
        index.search("Fed inflation in 2024"),
        false,
        "/test/context",
      ),
    ).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("accepts only allowed navigation text from a test model and rejects economic interpretation", async () => {
    const index = new EvidenceIndex();
    index.add([passage("p", "Inflation remains elevated.")]);
    const answer = index.search("Fed inflation in 2024");
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ sentence: allowedContextSentences(answer)[0] }),
        { status: 200 },
      ),
    );
    expect(
      await experimentalContextSentence(answer, true, "/test/context"),
    ).toBe(allowedContextSentences(answer)[0]);
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ sentence: "The Fed will cut rates earlier." }),
        { status: 200 },
      ),
    );
    await expect(
      experimentalContextSentence(answer, true, "/test/context"),
    ).rejects.toThrow("unsupported");
    expect(answer.passages[0].text).toBe("Inflation remains elevated.");
  });
  it("keeps all original809 quote records and date-verified expansion in the static shards", () => {
    const records = manifest.shards.flatMap(
      (shard) =>
        JSON.parse(
          gunzipSync(
            readFileSync(
              new URL(
                `../src/data/report-search/${shard.file}`,
                import.meta.url,
              ),
            ),
          ).toString(),
        ).passages,
    ) as EvidencePassage[];
    expect(records).toHaveLength(9390);
    expect(records.filter((p) => p.sourceType === "timeline")).toHaveLength(
      809,
    );
    expect(records.filter((p) => p.sourceType === "report")).toHaveLength(8581);
    expect(records.some((p) => p.kind === "press_conference")).toBe(false);
    expect(
      records.every(
        (p) =>
          /^https:\/\//.test(p.url) &&
          /^\d{4}-\d{2}-\d{2}$/.test(p.publishedOn),
      ),
    ).toBe(true);
    const index = new EvidenceIndex();
    index.add(records);
    expect(index.size).toBe(9390);
  });
  it("renders the not-found state without an answer assembled from unrelated sources", () => {
    const index = new EvidenceIndex();
    const answer: EvidenceAnswer = index.search(
      "underwater quantum basketball",
    );
    const html = renderToStaticMarkup(<EvidenceAnswerCard answer={answer} />);
    expect(html).toContain("Not found in these reports");
    expect(html).not.toContain("blockquote");
  });
});
