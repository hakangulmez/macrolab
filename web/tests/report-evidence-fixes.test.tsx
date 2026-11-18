import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  EvidenceIndex,
  planEvidenceSearch,
  type EvidencePassage,
} from "../src/reportSearch";
import { checkEvidenceSupport } from "../src/reportEvidenceSupport";
import { EvidenceAnswerCard } from "../src/components/AskReportPassages";
import manifest from "../src/data/report-search/manifest.json";

const pool = manifest.shards.flatMap(
  (s) =>
    JSON.parse(
      gunzipSync(
        readFileSync(
          new URL(`../src/data/report-search/${s.file}`, import.meta.url),
        ),
      ).toString(),
    ).passages,
) as EvidencePassage[];
const index = new EvidenceIndex();
index.add(pool);
const source = (text: string) => ({
  text,
  country: "USA",
  institution: "Fed",
  section: "Policy statement",
  kind: "statement",
});

describe("meeting dates and supported premises", () => {
  it("intersects meeting month with a separately specified release day", () => {
    const answer = index.search(
      "According to the July 2017 FOMC meeting minutes released on August 16, how did the Committee expect inflation to differ between the near term and medium term?",
    );
    expect(answer.status).toBe("found");
    expect(answer.passages.length).toBeGreaterThan(0);
    expect(
      answer.passages.every(
        (p) =>
          p.verifiedEventOn === "2017-07-26" && p.publishedOn === "2017-08-16",
      ),
    ).toBe(true);
  });
  it("resolves a Turkish month and PPK from event metadata", () => {
    const answer = index.search("Mart 2024 PPK ne karar aldı?");
    expect(answer.status).toBe("found");
    expect(answer.passages[0].verifiedEventOn).toBe("2024-03-21");
    expect(answer.passages[0].text).toContain("from 45 percent to 50 percent");
  });
  it("anchors the latest meeting to the corpus rather than the browser clock", () => {
    const plan = planEvidenceSearch(
      "What did the latest FOMC policy meeting decide?",
    );
    expect(plan.period.asOf).toBe("2026-11-17");
    expect(plan.period.resolvedMeetings.Fed).toBe("2026-10-28");
    const answer = index.search(
      "What did the latest FOMC policy meeting decide?",
    );
    expect(answer.status).toBe("comparison");
    expect(answer.comparisonPassages!.length).toBeGreaterThan(0);
    expect(
      answer.comparisonPassages!.every(
        (p) => p.verifiedEventOn === "2026-10-28",
      ),
    ).toBe(true);
  });
  it("retains an explicit year or as-of date on a relative meeting request", () => {
    expect(
      planEvidenceSearch("What did the latest FOMC meeting in 2024 decide?")
        .period.resolvedMeetings.Fed,
    ).toBe("2024-12-18");
    expect(
      planEvidenceSearch(
        "As of July 31, 2024, what did the last FOMC meeting decide?",
      ).period.resolvedMeetings.Fed,
    ).toBe("2024-07-31");
  });
  it("does not substitute older available minutes for missing latest-meeting minutes", () => {
    const answer = index.search(
      "What did the minutes of the latest FOMC meeting say about inflation?",
    );
    expect(answer.plan.period.resolvedMeetings.Fed).toBe("2026-10-28");
    expect(answer.status).toBe("not_found");
    expect(answer.passages).toEqual([]);
  });
  it("uses the audited ECB event date rather than its next-day publication", () => {
    const correct = index.search(
      "What did the ECB decide about securities markets at its meeting on 9 May 2010?",
    );
    expect(correct.passages.length).toBeGreaterThan(0);
    expect(correct.passages[0].verifiedEventOn).toBe("2010-05-09");
    expect(correct.passages[0].publishedOn).toBe("2010-05-10");
    const wrong = index.search(
      "What did the ECB decide about securities markets at its meeting on 10 May 2010?",
    );
    expect(wrong.passages).toEqual([]);
  });
  it("rejects invalid dates rather than selecting an adjacent meeting", () => {
    const answer = index.search(
      "What did the FOMC decide at its meeting on February 30, 2024?",
    );
    expect(answer.status).toBe("not_found");
    expect(answer.plan.period.unresolved).toContain("invalid");
  });
  it("does not treat a rising economy at a moderate rate as a policy-rate hike", () => {
    const p = source(
      "Economic activity has been rising at a moderate rate. The Committee decided to lower the target range for the federal funds rate.",
    );
    expect(
      checkEvidenceSupport("Why did the Fed raise its target range?", p)
        .supported,
    ).toBe(false);
  });
  it("does not treat risk language as a rate increase", () => {
    expect(
      checkEvidenceSupport(
        "Why did the Fed raise rates?",
        source("Risks remain. The Committee decided to lower its policy rate."),
      ).supported,
    ).toBe(false);
  });
  it("keeps dissenting preferences separate from the adopted amount", () => {
    const answer = index.search(
      "Why did Michelle Bowman prefer a three-quarter-percentage-point rate cut in the September 18, 2024 FOMC statement?",
    );
    expect(answer.status).toBe("not_found");
    expect(answer.passages).toEqual([]);
    expect(answer.relatedPassages.length).toBeGreaterThan(0);
    const html = renderToStaticMarkup(<EvidenceAnswerCard answer={answer} />);
    expect(html).toContain("Related, but not an answer");
    expect(html).not.toContain("data-evidence-id=");
    expect(html).toContain("data-related-id=");
  });
  it("binds purchases to their instruments rather than accepting swapped values", () => {
    const p = source(
      "The Committee decided to reduce monthly purchases of Treasury securities by $20 billion and agency mortgage-backed securities by $10 billion.",
    );
    expect(
      checkEvidenceSupport(
        "Why did the FOMC reduce purchases of Treasury securities by $10 billion and agency mortgage-backed securities by $20 billion?",
        p,
      ).supported,
    ).toBe(false);
    expect(
      checkEvidenceSupport(
        "Why did the FOMC reduce purchases of Treasury securities by $20 billion and agency mortgage-backed securities by $10 billion?",
        p,
      ).supported,
    ).toBe(true);
  });
  it("checks closed numeric questions and Unicode fractions without conflating 50 and75basispoints", () => {
    const p = source(
      "The Committee decided to lower its policy rate by ½ percentage point.",
    );
    expect(
      checkEvidenceSupport(
        "Did the Fed cut its policy rate by 75 basis points?",
        p,
      ).supported,
    ).toBe(false);
    expect(
      checkEvidenceSupport(
        "Did the Fed cut its policy rate by 50 basis points?",
        p,
      ).supported,
    ).toBe(true);
  });
  it("distinguishes an envelope increment from its total", () => {
    const p = {
      ...source(
        "The envelope will be increased by €500 billion to a total of €1850 billion.",
      ),
      institution: "ECB",
    };
    expect(
      checkEvidenceSupport(
        "Why did the ECB set the total envelope at €500 billion?",
        p,
      ).supported,
    ).toBe(false);
  });
  it("rejects a projection recast as an observed outcome", () => {
    const p = {
      ...source(
        "Inflation is set to remain below the target throughout 2021 and 2022.",
      ),
      institution: "OECD",
    };
    expect(
      checkEvidenceSupport(
        "What observed inflation result for 2022 did the OECD report?",
        p,
      ).supported,
    ).toBe(false);
  });
  it("does not count another variable's risk direction as support", () => {
    const p = {
      ...source(
        "Risks to inflation are tilted to the upside, while risks to growth are tilted to the downside.",
      ),
      institution: "ECB",
    };
    expect(
      checkEvidenceSupport(
        "Why did the ECB say risks to inflation were tilted to the downside while risks to growth were tilted to the upside?",
        p,
      ).supported,
    ).toBe(false);
  });
});

describe("comparison source lists and narrow premise regressions", () => {
  it("lists the negative deposit-rate source without relaxing its premise verifier", () => {
    const question =
      "When did the ECB first cut its deposit facility rate below zero, and to what level?";
    const answer = index.search(question);
    expect(answer.status).toBe("comparison");
    expect(answer.passages).toEqual([]);
    const list = answer.comparisonPassages!;
    expect(list.length).toBeGreaterThan(1);
    const expected = list.find(
      (p) => p.id === "timeline:ea-20140605-negative-deposit-rate:0",
    )!;
    expect(expected).toBeDefined();
    expect(checkEvidenceSupport(question, expected).supported).toBe(false);
    expect(expected.support!.reasons).toContain("unverified_comparison");
    expect(list.map((p) => p.verifiedEventOn ?? p.publishedOn)).toEqual(
      list.map((p) => p.verifiedEventOn ?? p.publishedOn).sort(),
    );
    const html = renderToStaticMarkup(<EvidenceAnswerCard answer={answer} />);
    expect(html).toContain(
      "Bu soru birden fazla kararın karşılaştırılmasını gerektiriyor; ilgili kararlar tarih sırasıyla aşağıda.",
    );
    expect(html).toContain("data-comparison-id=");
    expect(html).not.toContain("data-evidence-id=");
  });
  it.each([
    ["What was the highest ECB deposit rate?", "highest"],
    ["What was the lowest ECB deposit rate?", "lowest"],
    ["How many times did the ECB cut interest rates?", "count"],
    ["İlk ECB faiz kararı hangisi?", "first"],
    ["Son PPK kararı neydi?", "latest"],
    ["En yüksek ECB faizi neydi?", "highest"],
    ["En düşük ECB faizi neydi?", "lowest"],
    ["ECB kaç kez faiz indirdi?", "count"],
  ])("recognizes %s without generating a verdict", (q, operator) => {
    expect(planEvidenceSearch(q).comparison).toBe(operator);
  });
  it("does not interpret last year or first-stage as a decision comparison", () => {
    expect(
      planEvidenceSearch("What did the Fed say about inflation last year?")
        .comparison,
    ).toBeNull();
    expect(
      planEvidenceSearch("What was the first-stage regression?").comparison,
    ).toBeNull();
  });
  it("rejects a nominal increase while accepting a neutral question about the same decision", () => {
    expect(
      index.search(
        "What increase in the three key ECB interest rates did the Governing Council announce on June 5, 2025?",
      ).status,
    ).toBe("not_found");
    expect(
      index.search(
        "What change to the three key ECB interest rates did the Governing Council announce on June 5, 2025?",
      ).status,
    ).toBe("found");
  });
  it("binds the requested bank even if the named jurisdiction conflicts", () => {
    const a = index.search(
      "What US federal funds target range did the ECB Governing Council set on October 28, 2026?",
    );
    expect(a.plan.institutions).toEqual(["ECB"]);
    expect(a.status).toBe("not_found");
    expect(a.passages).toEqual([]);
  });
  it("does not erase explicit predicate negation", () => {
    const p = source(
      "Asset purchases are not on a preset course, and decisions remain contingent on the labor market and inflation outlook.",
    );
    expect(
      checkEvidenceSupport(
        "Why did the FOMC declare that asset purchases were on a preset course?",
        p,
      ).supported,
    ).toBe(false);
    expect(
      checkEvidenceSupport(
        "Why did the FOMC say asset purchases were not on a preset course?",
        p,
      ).supported,
    ).toBe(true);
  });
  it("keeps a false latest-meeting direction out of the comparison list", () => {
    const a = index.search(
      "As of the corpus manifest dated November 17, 2026, what were the reasons for the half-percentage-point rate cut at the latest FOMC policy meeting represented in the corpus?",
    );
    expect(a.status).toBe("not_found");
    expect(a.comparisonPassages).toEqual([]);
    expect(a.plan.period.asOf).toBe("2026-11-17");
  });
});
