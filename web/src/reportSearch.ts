/** Extractive lexical search. Ranking never writes or rewrites an economic answer. */
import {
  resolveEvidencePeriod,
  periodMatches,
  verifiedEvent,
  type EvidencePeriod,
} from "./reportEvidenceDates.ts";
import {
  checkEvidenceSupport,
  type EvidenceSupport,
} from "./reportEvidenceSupport.ts";
export interface EvidencePassage {
  id: string;
  sourceIds: string[];
  noteIds: string[];
  text: string;
  country: string;
  institution: string;
  title: string;
  kind: string;
  publishedOn: string;
  eventOn: string | null;
  url: string;
  section: string | null;
  speaker: string | null;
  region: string | null;
  scope: string;
  sourceType: "timeline" | "report";
  discovery: string;
}
export interface EvidenceFilters {
  countries?: string[];
  institution?: string;
  kind?: string;
  year?: string;
  publishedBy?: string;
}
export interface SearchPlan {
  comparison: "first" | "latest" | "highest" | "lowest" | "count" | null;
  countries: string[];
  institutions: string[];
  kinds: string[];
  years: string[];
  date: string | null;
  month: string | null;
  dateField: "publication" | "event";
  before: boolean;
  unsupported: boolean;
  terms: string[];
  filters: EvidenceFilters;
  period: EvidencePeriod;
}
export interface EvidenceHit extends EvidencePassage {
  score: number;
  verifiedEventOn: string | null;
  support?: EvidenceSupport;
}
export interface EvidenceAnswer {
  question: string;
  status: "found" | "not_found" | "partial" | "comparison";
  passages: EvidenceHit[];
  comparisonPassages?: EvidenceHit[];
  relatedPassages: EvidenceHit[];
  missingCountries: string[];
  plan: SearchPlan;
  elapsedMs: number;
}
const countries: Record<string, string[]> = {
  USA: ["United States", "United States of America", "American", "U.S.", "USA"],
  EA: ["euro area", "eurozone"],
  TUR: ["Türkiye", "Turkiye", "Turkey", "Turkish"],
  AUS: ["Australia", "Australian"],
  AUT: ["Austria", "Austrian"],
  BEL: ["Belgium", "Belgian"],
  CAN: ["Canada", "Canadian"],
  CHL: ["Chile", "Chilean"],
  COL: ["Colombia", "Colombian"],
  CRI: ["Costa Rica", "Costa Rican"],
  CZE: ["Czechia", "Czech Republic", "Czech"],
  DNK: ["Denmark", "Danish"],
  EST: ["Estonia", "Estonian"],
  FIN: ["Finland", "Finnish"],
  FRA: ["France", "French"],
  DEU: ["Germany", "German"],
  GRC: ["Greece", "Greek"],
  HUN: ["Hungary", "Hungarian"],
  ISL: ["Iceland", "Icelandic"],
  IRL: ["Ireland", "Irish"],
  ISR: ["Israel", "Israeli"],
  ITA: ["Italy", "Italian"],
  JPN: ["Japan", "Japanese"],
  KOR: ["Korea", "Korean", "South Korea"],
  LVA: ["Latvia", "Latvian"],
  LTU: ["Lithuania", "Lithuanian"],
  LUX: ["Luxembourg"],
  MEX: ["Mexico", "Mexican"],
  NLD: ["Netherlands", "Dutch"],
  NZL: ["New Zealand"],
  NOR: ["Norway", "Norwegian"],
  POL: ["Poland", "Polish"],
  PRT: ["Portugal", "Portuguese"],
  SVK: ["Slovakia", "Slovak Republic", "Slovak"],
  SVN: ["Slovenia", "Slovenian"],
  ESP: ["Spain", "Spanish"],
  SWE: ["Sweden", "Swedish"],
  CHE: ["Switzerland", "Swiss"],
  GBR: ["United Kingdom", "Britain", "British", "UK"],
};
const stop = new Set(
  "a an the and or of to in on at by for from with as is was were are be been being it its this that these those what which when where how why did does do say said report reports tell about according during compare comparison between describe described discuss discussed give show me please into than their they them has have had concerning regarding statement statements minutes fomc oecd fed ecb imf cbrt federal reserve economic outlook".split(
    " ",
  ),
);
// Conservative lexical equivalences only: earlier != smaller; could != will;
// unemployment != inflation; Treasury != agency debt != MBS.
const equivalences = [
  [
    "decide",
    "decides",
    "decided",
    "decision",
    "decisions",
    "agree",
    "agreed",
    "announce",
    "announced",
    "announcement",
  ],
  [
    "cut",
    "cuts",
    "cutting",
    "reduce",
    "reduces",
    "reduced",
    "reducing",
    "reduction",
    "reductions",
    "lower",
    "lowered",
    "lowering",
  ],
  [
    "increase",
    "increases",
    "increased",
    "increasing",
    "raise",
    "raises",
    "raised",
    "raising",
    "hike",
    "hikes",
    "hiked",
  ],
  [
    "forecast",
    "forecasts",
    "forecasting",
    "project",
    "projected",
    "projection",
    "projections",
    "expect",
    "expected",
    "expects",
    "expectation",
    "expectations",
  ],
  ["inflation", "inflationary", "prices", "price"],
  ["rate", "rates"],
  ["purchase", "purchases", "purchasing", "buy", "buying"],
  [
    "maintain",
    "maintained",
    "maintaining",
    "hold",
    "held",
    "holding",
    "unchanged",
  ],
  ["labour", "labor"],
  ["billion", "billions"],
  ["trillion", "trillions"],
];
const lexical = new Map(
  equivalences.flatMap((group) => group.map((word) => [word, group[0]])),
);
export function searchTokens(value: string): string[] {
  return (
    value
      .normalize("NFKC")
      .toLowerCase()
      .replace(/[’‘]/g, "'")
      .replace(/'s\b/g, "")
      .match(/[\p{L}]+(?:-[\p{L}]+)*|\d+(?:\.\d+)?/gu) ?? []
  )
    .filter((word) => !stop.has(word) && (word.length > 1 || /^\d$/.test(word)))
    .map((word) => lexical.get(word) ?? word);
}
const months = [
  "january",
  "february",
  "march",
  "april",
  "may",
  "june",
  "july",
  "august",
  "september",
  "october",
  "november",
  "december",
];
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function mentions(text: string, value: string) {
  return new RegExp(
    `(?:^|[^\\p{L}])${escape(value)}(?:$|[^\\p{L}])`,
    "iu",
  ).test(text);
}
export function planEvidenceSearch(
  question: string,
  filters: EvidenceFilters = {},
): SearchPlan {
  const q = question.normalize("NFKC");
  const folded = q
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/ı/g, "i");
  const comparison =
    /\b(?:how many times|how many (?:decisions|cuts|hikes)|kac kez|kac defa)\b/.test(
      folded,
    )
      ? "count"
      : /\b(?:highest|en yuksek)\b/.test(folded)
        ? "highest"
        : /\b(?:lowest|en dusuk)\b/.test(folded)
          ? "lowest"
          : /\b(?:first|earliest|ilk)\b(?![- ]stage)/.test(folded)
            ? "first"
            : /\b(?:latest|most recent|en son|son)\b|\blast\s+(?!year|month|week|quarter)\w+/.test(
                  folded,
                )
              ? "latest"
              : null;
  const foundCountries = Object.keys(countries).filter((id) =>
    countries[id].some((name) => mentions(q, name)),
  );
  if (/\bUS\b/.test(q) && !foundCountries.includes("USA"))
    foundCountries.push("USA");
  const institutions = [
    ["Fed", /\b(?:Fed|FOMC|Federal Reserve)\b/i],
    ["OECD", /\bOECD\b/i],
    ["ECB", /\bECB\b|European Central Bank/i],
    ["IMF", /\bIMF\b/i],
    ["CBRT", /\b(?:CBRT|PPK|TCMB)\b|Central Bank of (?:Turkey|Türkiye)/i],
  ]
    .filter(([, re]) => (re as RegExp).test(q))
    .map(([id]) => id as string);
  for (const [institution, country] of [
    ["Fed", "USA"],
    ["ECB", "EA"],
    ["CBRT", "TUR"],
  ]) {
    if (institutions.includes(institution) && !foundCountries.includes(country))
      foundCountries.push(country);
  }
  const explicitCountries = filters.countries?.filter(Boolean);
  const selectedCountries = explicitCountries?.length
    ? explicitCountries
    : foundCountries;
  let selectedInstitutions = filters.institution
    ? [filters.institution]
    : institutions;
  if (
    !filters.institution &&
    institutions.length === 1 &&
    selectedCountries.length > 1 &&
    /\b(?:compare|comparison|between|both)\b|karsilastir/i.test(folded) &&
    ["Fed", "ECB", "CBRT"].includes(institutions[0])
  )
    selectedInstitutions = [];
  const kinds = filters.kind
    ? [filters.kind]
    : /\bminutes\b/i.test(q)
      ? ["minutes"]
      : /\bstatement\b/i.test(q)
        ? ["statement", "policy_release"]
        : /\b(?:SLOOS|loan officer survey)\b/i.test(q)
          ? ["sloos"]
          : /\bbeige book\b/i.test(q)
            ? ["beige_book"]
            : [];
  const period = resolveEvidencePeriod(
    q,
    selectedInstitutions,
    selectedCountries,
    filters,
  );
  const primary = period.eventRequired ? period.event : period.publication;
  const date = primary.date ?? period.publishedBefore;
  const month = primary.month;
  const before = Boolean(period.publishedBefore);
  const years = before
    ? []
    : [
        ...new Set([
          ...period.event.years,
          ...period.publication.years,
          ...[
            period.event.date,
            period.event.month,
            period.publication.date,
            period.publication.month,
            ...Object.values(period.resolvedMeetings),
          ]
            .filter((d): d is string => Boolean(d))
            .map((d) => d.slice(0, 4)),
        ]),
      ];
  const unsupportedCountry = [
    "Brazil",
    "China",
    "India",
    "Russia",
    "Argentina",
    "South Africa",
    "Kenya",
    "Ethiopia",
  ].some((c) => mentions(q, c));
  const unsupportedInstitution =
    /\b(?:BIS|World Bank|Bank of England|Bank of Japan)\b/i.test(q) &&
    institutions.length === 0;
  const terms = [...new Set(searchTokens(q))].filter(
    (t) =>
      !/^\d{4}$/.test(t) &&
      !months.includes(t) &&
      !months.some((m) => m.slice(0, 3) === t),
  );
  if (/\bPPK\b/i.test(q) || /faiz|karar|toplantı/i.test(q))
    terms.push("rate", "decided");
  return {
    comparison,
    countries: selectedCountries,
    institutions: selectedInstitutions,
    kinds,
    years,
    date,
    month,
    dateField: period.eventRequired ? "event" : "publication",
    before,
    unsupported:
      unsupportedCountry ||
      unsupportedInstitution ||
      selectedCountries.some((c) => !countries[c]) ||
      Boolean(period.unresolved) ||
      Boolean(
        years.length &&
        years.every((y) => y < "2009" || y > period.asOf.slice(0, 4)),
      ),
    terms,
    filters,
    period,
  };
}
export function passageMatches(p: EvidencePassage, plan: SearchPlan): boolean {
  if (
    plan.unsupported ||
    (plan.countries.length && !plan.countries.includes(p.country)) ||
    (plan.institutions.length && !plan.institutions.includes(p.institution)) ||
    (plan.kinds.length && !plan.kinds.includes(p.kind))
  )
    return false;
  if (plan.filters.publishedBy && p.publishedOn > plan.filters.publishedBy)
    return false;
  return periodMatches(p, plan.period);
}
interface Indexed {
  passage: EvidencePassage;
  frequencies: Map<string, number>;
  length: number;
  body: Set<string>;
}
export class EvidenceIndex {
  private rows = new Map<string, Indexed>();
  add(passages: EvidencePassage[]) {
    for (const passage of passages) {
      if (this.rows.has(passage.id)) continue;
      if (
        !passage.text.trim() ||
        !/^https:\/\//.test(passage.url) ||
        !/^\d{4}-\d{2}-\d{2}$/.test(passage.publishedOn)
      )
        throw new Error("Invalid evidence record");
      const bodyTokens = searchTokens(passage.text);
      const meta = searchTokens(
        `${passage.title} ${passage.section ?? ""} ${passage.discovery} ${passage.region ?? ""}`,
      );
      const frequencies = new Map<string, number>();
      for (const token of [...bodyTokens, ...meta, ...meta])
        frequencies.set(token, (frequencies.get(token) ?? 0) + 1);
      this.rows.set(passage.id, {
        passage,
        frequencies,
        length: bodyTokens.length + meta.length * 2,
        body: new Set(bodyTokens),
      });
    }
  }
  get size() {
    return this.rows.size;
  }
  search(
    question: string,
    filters: EvidenceFilters = {},
    limit = 5,
  ): EvidenceAnswer {
    const started = performance.now();
    const plan = planEvidenceSearch(question, filters);
    const decisionIntent =
      plan.institutions.some((i) => ["Fed", "ECB", "CBRT"].includes(i)) &&
      /\b(?:announc\w*|decid\w*|agree\w*|target range|funds target|policy action|cut\w*|rais\w*|hike\w*|PPK)\b|karar|faiz/i.test(
        question,
      ) &&
      !plan.kinds.includes("minutes");
    const candidates = [...this.rows.values()].filter(
      (r) =>
        passageMatches(r.passage, plan) &&
        (!decisionIntent ||
          ["statement", "policy_release"].includes(r.passage.kind)),
    );
    const reports = new Map<string, Indexed>();
    const reportsByUrl = new Map<string, Indexed[]>();
    for (const row of candidates)
      if (row.passage.sourceType === "report") {
        for (const id of row.passage.sourceIds) reports.set(id, row);
        const url = row.passage.url.split("#")[0];
        reportsByUrl.set(url, [...(reportsByUrl.get(url) ?? []), row]);
      }
    const merged = new Map<string, Indexed>();
    const eligible: Indexed[] = [];
    for (const row of candidates) {
      const complete =
        row.passage.sourceType === "timeline"
          ? [
              ...row.passage.sourceIds.map((id) => reports.get(id)),
              ...(reportsByUrl.get(row.passage.url.split("#")[0]) ?? []),
            ].find(
              (r) =>
                r &&
                r.passage.country === row.passage.country &&
                r.passage.publishedOn === row.passage.publishedOn &&
                r.passage.text.includes(row.passage.text),
            )
          : undefined;
      if (complete) {
        // A short timeline excerpt must not suppress its fuller source passage.
        // Only ranking metadata is combined; output is the unchanged original.
        const target = merged.get(complete.passage.id) ?? {
          ...complete,
          frequencies: new Map(complete.frequencies),
        };
        for (const [term, count] of row.frequencies)
          target.frequencies.set(
            term,
            (target.frequencies.get(term) ?? 0) + count,
          );
        merged.set(complete.passage.id, target);
      } else eligible.push(row);
    }
    for (let i = 0; i < eligible.length; i++)
      eligible[i] = merged.get(eligible[i].passage.id) ?? eligible[i];
    const df = new Map(
      plan.terms.map((term) => [
        term,
        eligible.reduce((n, row) => n + Number(row.frequencies.has(term)), 0),
      ]),
    );
    const averageLength =
      eligible.reduce((n, row) => n + row.length, 0) /
      Math.max(1, eligible.length);
    const scored: EvidenceHit[] = [];
    for (const row of eligible) {
      let score = 0,
        bodyMatches = 0;
      for (const term of plan.terms) {
        const tf = row.frequencies.get(term) ?? 0;
        if (!tf) continue;
        if (row.body.has(term)) bodyMatches++;
        const idf = Math.log(
          1 +
            (eligible.length - (df.get(term) ?? 0) + 0.5) /
              ((df.get(term) ?? 0) + 0.5),
        );
        score +=
          (idf * (tf * 2.2)) /
          (tf +
            1.2 * (0.25 + (0.75 * row.length) / Math.max(1, averageLength)));
      }
      // A decision question should prefer the actual release over later discussion.
      if (decisionIntent && row.passage.kind === "statement") score *= 2.5;
      if (score > 0 && bodyMatches >= 1)
        scored.push({
          ...row.passage,
          score,
          verifiedEventOn: verifiedEvent(row.passage).date,
        });
    }
    scored.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
    const contextKey = (p: EvidenceHit) =>
      JSON.stringify([
        p.country,
        p.url.split("#")[0],
        p.publishedOn,
        p.verifiedEventOn,
      ]);
    const contexts = new Map<string, EvidenceHit[]>();
    for (const p of scored) {
      const key = contextKey(p);
      const group = contexts.get(key);
      if (group) group.push(p);
      else contexts.set(key, [p]);
    }
    const checked = new Map<string, EvidenceSupport>();
    for (const p of scored) {
      const document = contextKey(p),
        key = `${document}:${p.section ?? ""}`;
      if (!checked.has(key))
        checked.set(
          key,
          checkEvidenceSupport(question, p, contexts.get(document)),
        );
      p.support = checked.get(key);
    }
    if (plan.comparison) {
      // This is a source list, never a verdict about a superlative or a count.
      // Latest-meeting questions retain the existing event and premise checks.
      const operator = plan.comparison;
      const bodyTerms = plan.terms.filter(
        (t) =>
          ![
            "first",
            "earliest",
            "latest",
            "last",
            "highest",
            "lowest",
            "many",
            "times",
            "below",
            "zero",
          ].includes(t),
      );
      const instrument = /deposit (?:facility|rate)/i.test(question)
        ? /deposit (?:facility|rate)/i
        : null;
      const matching = scored.filter(
        (p) =>
          (operator !== "latest" || p.support?.supported) &&
          (!instrument || instrument.test(p.text)) &&
          bodyTerms.some((t) => searchTokens(p.text).includes(t)),
      );
      // A leading contradictory premise still prevents a latest-decision answer.
      const comparisonPassages =
        operator === "latest" && !scored[0]?.support?.supported ? [] : matching;
      comparisonPassages.sort(
        (a, b) =>
          (a.verifiedEventOn ?? a.publishedOn).localeCompare(
            b.verifiedEventOn ?? b.publishedOn,
          ) || a.id.localeCompare(b.id),
      );
      return {
        question,
        status: comparisonPassages.length ? "comparison" : "not_found",
        passages: [],
        comparisonPassages,
        relatedPassages: comparisonPassages.length ? [] : scored.slice(0, 5),
        missingCountries: plan.countries.filter(
          (c) => !comparisonPassages.some((p) => p.country === c),
        ),
        plan,
        elapsedMs: performance.now() - started,
      };
    }
    // A high relevance score is not evidence for the question's premise.
    // If the leading passage fails the explicit checks, do not promote another
    // loosely related quotation into an answer. Keep context separately labelled.
    const leadingSupported = scored[0]?.support?.supported ?? false;
    const answerable = leadingSupported
      ? scored.filter((p) => p.support?.supported)
      : [];
    const selected: EvidenceHit[] = [];
    const duplicate = (p: EvidenceHit) =>
      selected.some(
        (s) =>
          s.country === p.country &&
          s.publishedOn === p.publishedOn &&
          (s.text.includes(p.text) || p.text.includes(s.text)),
      );
    if (decisionIntent && answerable[0]?.kind === "statement") {
      const sourceDocument = (p: EvidenceHit) =>
        p.sourceIds
          .find((id) => id.startsWith("fed-statement-"))
          ?.split(":")[0];
      const document = sourceDocument(answerable[0]);
      if (document) {
        // Retrieve the related paragraphs of an adopted decision together.
        // This preserves the range, purchase terms and dissent context rather
        // than filling the result list with repetitions from later minutes.
        const room = Math.min(
          3,
          limit - Math.max(0, plan.countries.length - 1),
        );
        const related = answerable
          .filter(
            (p) => p.sourceType === "report" && sourceDocument(p) === document,
          )
          .sort((a, b) => a.id.localeCompare(b.id));
        for (const p of related.slice(0, room))
          if (!duplicate(p)) selected.push(p);
      }
    }
    if (plan.countries.length > 1)
      for (const country of plan.countries) {
        const p = answerable.find((hit) => hit.country === country);
        if (p && selected.length < limit && !duplicate(p)) selected.push(p);
      }
    for (const p of answerable) {
      if (selected.length >= limit) break;
      if (!duplicate(p)) selected.push(p);
    }
    const missingCountries = plan.countries.filter(
      (country) => !selected.some((p) => p.country === country),
    );
    return {
      question,
      status: selected.length
        ? missingCountries.length
          ? "partial"
          : "found"
        : "not_found",
      passages: selected,
      relatedPassages: scored
        .filter((p) => !p.support?.supported || !leadingSupported)
        .slice(0, 5),
      missingCountries,
      plan,
      elapsedMs: performance.now() - started,
    };
  }
}

/** A test model may choose a navigation sentence; it can never write an economic claim. */
export function allowedContextSentences(answer: EvidenceAnswer): string[] {
  const names = [
    ...new Set(
      answer.passages.map((p) => countries[p.country]?.[0] ?? p.country),
    ),
  ].join(" and ");
  return answer.status === "found"
    ? [
        `The passages below are from reports about ${names}.`,
        `The selected source passages for ${names} are shown below.`,
      ]
    : [];
}
export async function experimentalContextSentence(
  answer: EvidenceAnswer,
  enabled: boolean,
  endpoint: string,
  signal?: AbortSignal,
): Promise<string | null> {
  if (!enabled || !endpoint || answer.status !== "found") return null;
  if (!endpoint.startsWith("/") || endpoint.startsWith("//"))
    throw new Error("Only a local test endpoint is supported");
  const allowed = allowedContextSentences(answer);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task: "Choose one allowed navigation sentence. Do not summarize, infer, or alter economic claims.",
      allowedSentences: allowed,
      evidence: answer.passages.map((p) => ({
        id: p.id,
        country: p.country,
        publishedOn: p.publishedOn,
        quote: p.text,
      })),
    }),
    signal,
  });
  if (!response.ok)
    throw new Error("The experimental context sentence is unavailable");
  const value = (await response.json()) as { sentence?: unknown };
  if (typeof value.sentence !== "string" || !allowed.includes(value.sentence))
    throw new Error(
      "The experimental sentence added unsupported content and was rejected",
    );
  return value.sentence;
}
