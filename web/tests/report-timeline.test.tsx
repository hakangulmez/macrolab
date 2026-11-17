import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  EconomicTimeline,
  ReportTimeline,
} from "../src/components/ReportTimeline";
import original from "../src/data/report-timeline-pilot.json";
import reviewed from "../src/data/report-timeline-reviewed.json";
import regions from "../src/data/report-timeline-regions.json";
import additions from "../src/data/report-timeline-countries.json";
import {
  periodBoundary,
  reportNotes,
  timelineForResult,
  timelineHighlights,
  chronologyForCountry,
  chronologyCoverage,
  reportTopicsForResult,
  reportCountries,
  type ReportNote,
} from "../src/reportTimeline";
import type { AnalysisResult } from "../src/types";

function analysis(model = "sing.ols"): AnalysisResult {
  return {
    status: "ok",
    config_hash: "timeline-test",
    config: {
      countries: ["USA"],
      series: [
        { concept_id: "cpi", role: "dependent", transform: "yoy" },
        { concept_id: "policy_rate", role: "regressor", transform: "level" },
      ],
      model: { id: model, params: {} },
      sample: { start: "2009-01", end: "2026-12" },
    },
    results: [
      {
        country: "USA",
        status: "ok",
        actual_sample: { start: "2009-01", end: "2026-09" },
        forecast: { origin: "2026-09" },
      },
    ],
    actual_samples: {},
  } as unknown as AnalysisResult;
}

describe("source-backed report timeline", () => {
  it("renders the standalone archive with no result or analysis request", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    try {
      const html = renderToStaticMarkup(<EconomicTimeline />);
      expect(html).toContain('data-testid="screen-timeline"');
      expect(html).toContain(
        'id="report-context-heading">Economic timeline</h1>',
      );
      expect(html).toContain("United States");
      expect(html).toContain("Euro area");
      expect(html).toContain("Türkiye");
      expect(html).toContain("Timeline year");
      expect(html).toContain("2009");
      expect(html).toContain("17 Nov 2026");
      expect(html.match(/data-note-id=/g)).toHaveLength(6);
      expect(html).not.toContain("Analysis period");
      expect(html).not.toContain("your analysis sample");
      expect(fetch).not.toHaveBeenCalled();
    } finally {
      fetch.mockRestore();
    }
  });
  it("uses real calendar period boundaries, including leap years", () => {
    expect(periodBoundary("2020-02", true)).toBe("2020-02-29");
    expect(periodBoundary("2021-Q1", true)).toBe("2021-03-31");
    expect(periodBoundary("2021-Q4", false)).toBe("2021-10-01");
    expect(periodBoundary("2021", true)).toBe("2021-12-31");
    expect(periodBoundary("2021-02-30", true)).toBeNull();
    expect(periodBoundary("latest", true)).toBeNull();
  });

  it("bounds historical context by actual data, not just the requested end", () => {
    const result = analysis();
    const before = JSON.stringify(result);
    const context = timelineForResult(result)!;
    expect(context.end).toBe("2026-09-30");
    expect(context.notes.some((n) => n.publishedOn === "2026-10-28")).toBe(
      false,
    );
    expect(context.notes.some((n) => n.publishedOn === "2026-09-23")).toBe(
      true,
    );
    expect(JSON.stringify(result)).toBe(before);
  });

  it("filters by publication date rather than an earlier meeting date", () => {
    const result = analysis("fc.var");
    result.results[0].forecast = { origin: "2021-Q1" };
    const context = timelineForResult(result)!;
    expect(context.end).toBe("2021-03-31");
    const minutes = reportNotes.find(
      (n) => n.source.documentId === "fed-minutes-20210317",
    )!;
    expect(minutes.eventOn).toBe("2021-03-17");
    expect(minutes.publishedOn).toBe("2021-04-07");
    expect(context.notes).not.toContainEqual(minutes);
    expect(context.notes.every((n) => n.publishedOn <= context.end!)).toBe(
      true,
    );
    result.results[0].forecast = { origin: "2021-04" };
    expect(timelineForResult(result)!.notes).toContainEqual(minutes);
  });

  it("does not substitute event dates when publication is unknown", () => {
    const note = { ...reportNotes[0], publishedOn: "" } as ReportNote;
    expect(timelineForResult(analysis(), [note])!.notes).toEqual([]);
    note.publishedOn = "2021-02-30";
    expect(timelineForResult(analysis(), [note])!.notes).toEqual([]);
  });

  it("bounds notes by the later actual sample start", () => {
    const result = analysis();
    result.results[0].actual_sample.start = "2020-Q2";
    const context = timelineForResult(result)!;
    expect(context.start).toBe("2020-04-01");
    expect(context.notes.length).toBeGreaterThan(0);
    expect(context.notes.every((n) => n.publishedOn >= context.start!)).toBe(
      true,
    );
  });

  it("preserves every original note and excludes unverified and duplicate candidates", () => {
    expect(reportNotes.slice(0, 28)).toEqual(original.notes);
    expect(reportNotes.slice(28, 57)).toEqual(reviewed.notes);
    expect(reportNotes.length).toBeGreaterThan(57);
    expect(new Set(reportNotes.map((n) => n.id)).size).toBe(reportNotes.length);
    expect(
      reportNotes.some((n) => n.source.documentId.startsWith("fed-press")),
    ).toBe(false);
    for (const id of ["c05p01-v2-n03", "c21p01-v2-n03", "c24p01-v2-n01"]) {
      expect(reportNotes.some((n) => n.id === `reviewed-${id}`)).toBe(false);
    }
    for (const note of reportNotes.slice(28, 57)) {
      expect(note.actor).toBeTruthy();
      expect(note.source.publicationEvidenceUrl).toMatch(/^https:\/\//);
      expect(note.source.passages?.length).toBeGreaterThan(0);
      expect(periodBoundary(note.publishedOn, false)).toBe(note.publishedOn);
    }
  });

  it("selects at most six distinct reports across the chronological period", () => {
    const notes = timelineForResult(analysis())!.notes;
    const before = JSON.stringify(notes);
    const highlights = timelineHighlights(notes);
    expect(highlights).toHaveLength(6);
    expect(new Set(highlights.map((n) => n.source.documentId)).size).toBe(6);
    expect(highlights[0].publishedOn).toBe(notes[0].publishedOn);
    expect(highlights.at(-1)!.publishedOn).toBe(notes.at(-1)!.publishedOn);
    expect(highlights.map((n) => n.publishedOn)).toEqual(
      highlights.map((n) => n.publishedOn).sort(),
    );
    expect(JSON.stringify(notes)).toBe(before);
    expect(timelineHighlights([])).toEqual([]);
    expect(timelineHighlights(notes, 0)).toEqual([]);
  });

  it("fails closed for unknown forecast origins and rolling evaluations", () => {
    const result = analysis("uni.arima");
    result.results[0].forecast = {};
    expect(timelineForResult(result)!.notes).toEqual([]);
    expect(timelineForResult(result)!.message).toContain("origin");
    const evaluation = timelineForResult(analysis("fc.eval"))!;
    expect(evaluation.notes).toEqual([]);
    expect(evaluation.message).toContain("individual rolling forecast origins");
  });

  it("restricts analysis context to supported regions and selected economic variables", () => {
    const result = analysis();
    result.config.countries = ["BRA"];
    expect(timelineForResult(result)).toBeNull();
    result.config.countries = ["USA"];
    result.config.series = [
      { concept_id: "unknown_concept", role: "dependent", transform: "level" },
    ];
    expect(timelineForResult(result)).toBeNull();
    result.config.series = [
      { concept_id: "policy_rate", role: "dependent", transform: "level" },
    ];
    const context = timelineForResult(result)!;
    expect(context.topics).toEqual(["policy_rate"]);
    expect(context.notes.every((n) => n.topics.includes("policy_rate"))).toBe(
      true,
    );
  });

  it("provides source-linked notes in every year for all three regional archives", () => {
    const expectedYears = Array.from({ length: 18 }, (_, i) =>
      String(2009 + i),
    );
    for (const country of ["USA", "EA", "TUR"] as const) {
      const archive = chronologyForCountry(country);
      expect([
        ...new Set(archive.notes.map((n) => n.publishedOn.slice(0, 4))),
      ]).toEqual(expectedYears);
      expect(archive.end).toBe("2026-11-17");
      expect(archive.notes.every((n) => n.country === country)).toBe(true);
      for (const note of archive.notes) {
        expect(note.source.quote.length).toBeGreaterThan(15);
        expect(note.source.url).toMatch(/^https:\/\//);
        expect(note.source.publicationEvidenceUrl).toMatch(/^https:\/\//);
        expect(note.publishedOn <= chronologyCoverage.asOf).toBe(true);
      }
    }
  });

  it("extends all MacroLab countries while preserving the original 154 notes", () => {
    expect(reportNotes.slice(0, 154)).toEqual([
      ...original.notes,
      ...reviewed.notes,
      ...regions.notes,
    ]);
    expect(reportCountries).toHaveLength(39);
    expect(new Set(reportCountries).size).toBe(39);
    expect(reportNotes).toHaveLength(801);
    expect(additions.notes).toHaveLength(647);
    for (const country of reportCountries) {
      const archive = chronologyForCountry(country);
      const years = new Set(
        archive.notes.map((note) => note.publishedOn.slice(0, 4)),
      );
      expect(archive.notes.length).toBeGreaterThan(0);
      expect(years.size).toBe(country === "CRI" ? 17 : 18);
      for (const note of archive.notes) {
        expect(note.country).toBe(country);
        expect(note.source.quote.length).toBeGreaterThan(15);
        expect(note.source.url).toMatch(/^https:\/\//);
        expect(note.source.publicationEvidenceUrl).toMatch(/^https:\/\//);
        expect(periodBoundary(note.publishedOn, false)).toBe(note.publishedOn);
      }
    }
    expect(chronologyCoverage.byCountry.CRI.missingYears).toEqual(["2012"]);
    expect(
      chronologyForCountry("CRI").notes.some((note) =>
        note.publishedOn.startsWith("2012"),
      ),
    ).toBe(false);
  });

  it("supports new countries without crossing country or forecast publication cutoffs", () => {
    const result = analysis("fc.var");
    result.config.countries = ["CAN", "JPN"];
    result.results = result.config.countries.map((country) => ({
      ...result.results[0],
      country,
      forecast: { origin: "2022-Q1" },
    }));
    const before = JSON.stringify(result);
    for (const country of ["CAN", "JPN"] as const) {
      const context = timelineForResult(result, undefined, country)!;
      expect(context.country).toBe(country);
      expect(context.end).toBe("2022-03-31");
      expect(context.notes.length).toBeGreaterThan(0);
      expect(
        context.notes.every(
          (note) =>
            note.country === country && note.publishedOn <= context.end!,
        ),
      ).toBe(true);
    }
    expect(JSON.stringify(result)).toBe(before);
    expect(timelineForResult(result, undefined, "DEU")).toBeNull();
  });

  it("keeps EA and Türkiye evidence separate from US evidence", () => {
    for (const country of ["EA", "TUR"] as const) {
      const result = analysis();
      result.config.countries = [country];
      result.results[0].country = country;
      const context = timelineForResult(result)!;
      expect(context.country).toBe(country);
      expect(context.notes.length).toBeGreaterThan(0);
      expect(context.notes.every((n) => n.country === country)).toBe(true);
      expect(context.notes.some((n) => n.source.institution === "Fed")).toBe(
        false,
      );
      expect(timelineForResult(result, undefined, "USA")).toBeNull();
    }
  });

  it("links spanning OECD chunks to the actual quoted PDF page", () => {
    for (const [id, page] of [
      ["tur-20090624-oecd-inflation", "176"],
      ["tur-20100526-oecd-growth", "191"],
      ["tur-20111128-oecd-fiscal", "190"],
    ]) {
      const note = reportNotes.find((n) => n.id === id)!;
      expect(note.source.url).toContain(`#page=${page}`);
    }
  });

  it("excludes future-dated publications from the full archive as well", () => {
    const future = { ...reportNotes[0], publishedOn: "2026-11-18" };
    expect(chronologyForCountry("USA", [future]).notes).toEqual([]);
  });

  it("uses country-specific sample and forecast cutoffs in comparisons", () => {
    const result = analysis("fc.var");
    result.config.countries = ["USA", "TUR"];
    result.results.push({
      ...result.results[0],
      country: "TUR",
      forecast: { origin: "2020-Q1" },
    });
    result.actual_samples = {
      TUR: {
        ...result.results[0].actual_sample,
        start: "2012-Q1",
        end: "2020-Q4",
        nobs: 36,
      },
    };
    const context = timelineForResult(result, undefined, "TUR")!;
    expect(context.start).toBe("2012-01-01");
    expect(context.end).toBe("2020-03-31");
    expect(context.notes.length).toBeGreaterThan(0);
    expect(
      context.notes.every(
        (n) => n.publishedOn >= context.start! && n.publishedOn <= context.end!,
      ),
    ).toBe(true);
  });

  it("maps real MacroLab indicator identifiers to economic topics", () => {
    const result = analysis();
    for (const [concept, expected] of [
      ["gdp_real", "growth"],
      ["ind_prod", "growth"],
      ["unemp", "labour"],
      ["credit_pnfs", "credit"],
      ["fx_usd", "exchange_rate"],
      ["gov_balance", "fiscal"],
      ["ca_gdp", "trade"],
      ["gdp_defl", "inflation"],
      ["rate_10y", "policy_rate"],
    ]) {
      result.config.series = [
        { concept_id: concept, role: "dependent", transform: "level" },
      ];
      expect(reportTopicsForResult(result)).toContain(expected);
    }
  });

  it("offers an explicitly separate full chronology without changing forecast context", () => {
    const result = analysis("uni.arima");
    result.results[0].forecast = { origin: "2021-Q1" };
    const before = JSON.stringify(result);
    const bounded = timelineForResult(result)!;
    const archive = chronologyForCountry("USA");
    expect(bounded.end).toBe("2021-03-31");
    expect(archive.notes.some((n) => n.publishedOn > bounded.end!)).toBe(true);
    expect(archive.end).toBe("2026-11-17");
    expect(JSON.stringify(result)).toBe(before);
    const html = renderToStaticMarkup(<ReportTimeline result={result} />);
    expect(html).toContain("Explore chronology");
    expect(html).toContain("Chronology country");
    expect(html).not.toContain('data-testid="report-archive-scope"');
  });

  it("keeps source arrays immutable and publication ordering chronological", () => {
    const before = JSON.stringify(reportNotes);
    const context = timelineForResult(analysis())!;
    expect(context.notes.map((n) => n.publishedOn)).toEqual(
      context.notes.map((n) => n.publishedOn).sort(),
    );
    expect(JSON.stringify(reportNotes)).toBe(before);
    expect(
      new Set(reportNotes.map((n) => n.publishedOn.slice(0, 4))).size,
    ).toBe(18);
  });

  it("renders compact notes, original evidence and dates without network calls", () => {
    const spy = vi.spyOn(globalThis, "fetch");
    try {
      const html = renderToStaticMarkup(<ReportTimeline result={analysis()} />);
      expect(html).toContain("Historical context");
      expect(html).toContain("Timeline year");
      expect(html).toContain("View source passage");
      expect(html).toContain("OECD");
      expect(html).toContain("Forecast");
      expect(html).toContain("not an announced Fed decision");
      expect(html.match(/data-note-id=/g)).toHaveLength(6);
      expect(html).toContain("Show all");
      expect(html).not.toContain("<details open");
      expect(spy).not.toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });

  it("states unsupported coverage instead of inventing notes outside the pilot", () => {
    const result = analysis();
    result.config.sample = { start: "2008-01", end: "2008-12" };
    result.results[0].actual_sample.start = "2008-01";
    result.results[0].actual_sample.end = "2008-12";
    const html = renderToStaticMarkup(<ReportTimeline result={result} />);
    expect(html).toContain("No selected notes match");
    expect(html).not.toContain("data-note-id");
    expect(html).toContain("2009–2026");
  });
});
