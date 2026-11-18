import { reportMeetingCatalog } from "./data/report-meeting-catalog.ts";

interface DatedPassage {
  id: string;
  sourceIds: string[];
  eventOn: string | null;
  institution: string;
  country: string;
  publishedOn: string;
}
export interface DateConstraint {
  date: string | null;
  month: string | null;
  years: string[];
  dayOfMonth: string | null;
}
export interface EvidencePeriod {
  asOf: string;
  eventRequired: boolean;
  event: DateConstraint;
  publication: DateConstraint;
  publishedBefore: string | null;
  resolvedMeetings: Record<string, string>;
  relative: "latest" | "previous" | null;
  unresolved: string | null;
}
const aliases = [
  ["january", "jan", "ocak"],
  ["february", "feb", "subat"],
  ["march", "mar", "mart"],
  ["april", "apr", "nisan"],
  ["may", "mayis"],
  ["june", "jun", "haziran"],
  ["july", "jul", "temmuz"],
  ["august", "aug", "agustos"],
  ["september", "sep", "sept", "eylul"],
  ["october", "oct", "ekim"],
  ["november", "nov", "kasim"],
  ["december", "dec", "aralik"],
];
const monthNames = aliases
  .flat()
  .sort((a, b) => b.length - a.length)
  .join("|");
const fold = (s: string) =>
  s.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/ı/g, "i");
const monthNumber = (s: string) =>
  String(aliases.findIndex((a) => a.includes(s)) + 1).padStart(2, "0");
const blank = (): DateConstraint => ({
  date: null,
  month: null,
  years: [],
  dayOfMonth: null,
});
const meetingWords =
  /\b(?:meeting|fomc|mpc|ppk|toplanti|toplantisi|toplantida)\b/;

export function verifiedEvent(p: DatedPassage) {
  const explicit = reportMeetingCatalog.byPassage[p.id];
  const source = p.sourceIds
    .map((id) => reportMeetingCatalog.bySource[id.split(":")[0]])
    .find(Boolean);
  const meta = explicit ?? source;
  return {
    date: meta?.date ?? p.eventOn,
    type: meta?.type ?? null,
    meeting: meta?.meeting ?? Boolean(p.eventOn),
  };
}

export function resolveEvidencePeriod(
  question: string,
  institutions: string[],
  countries: string[],
  filters: { year?: string; publishedBy?: string } = {},
): EvidencePeriod {
  let q = fold(question).replace(/(?<=[a-z])-(?=[a-z])/g, " ");
  // A corpus/as-of date bounds available evidence; it is not a meeting date.
  const asOf =
    /\bas of\s+(?:(?:the|its)\s+)?(?:corpus manifest dated\s+)?((?:[a-z]+\s+\d{1,2},?\s+20\d{2})|(?:20\d{2}-\d{2}-\d{2}))(?:\s+(?:corpus\s+)?manifest)?/.exec(
      q,
    );
  const cutoffDate = asOf
    ? new Date(
        asOf[1].includes("-") ? `${asOf[1]}T00:00:00Z` : `${asOf[1]} UTC`,
      )
    : null;
  if (asOf && cutoffDate && !Number.isNaN(cutoffDate.getTime()))
    q = q.replace(asOf[0], " ");
  const policy = institutions.some((i) => ["Fed", "ECB", "CBRT"].includes(i));
  const eventIntent =
    meetingWords.test(q) ||
    (policy && /\b(?:decid\w*|decision|policy action|karar|faiz)\b/.test(q));
  const result: EvidencePeriod = {
    asOf: reportMeetingCatalog.asOf,
    eventRequired: eventIntent,
    event: blank(),
    publication: blank(),
    publishedBefore: null,
    resolvedMeetings: {},
    relative: null,
    unresolved: null,
  };
  if (cutoffDate && !Number.isNaN(cutoffDate.getTime())) {
    const cutoff = cutoffDate.toISOString().slice(0, 10);
    if (cutoff > result.asOf)
      result.unresolved = "That cutoff is beyond the reviewed corpus.";
    else result.asOf = cutoff;
  }
  if (
    /\b(?:meeting|toplanti\w*)\s+(?:after|following|sonraki)\b/.test(q) ||
    /\b(?:after|following)\s+(?:its|the)\s+first\b/.test(q)
  ) {
    result.unresolved =
      "The selected archive does not establish the next actual meeting after that event.";
    return result;
  }
  const relative =
    /\b(?:latest|last|most recent|en son|son)\s+(?:(?:fomc|fed|ecb|ppk|mpc|monetary|policy|committee)\s+){0,4}(?:meeting|decision|toplanti\w*|karar\w*)\b/.test(
      q,
    );
  const previous =
    /\b(?:previous|preceding|bir onceki)\s+(?:(?:fomc|ecb|ppk|mpc)\s+)?(?:meeting|toplanti\w*)\b/.test(
      q,
    );
  if (relative || previous) {
    result.relative = previous ? "previous" : "latest";
    result.eventRequired = true;
    const selected = institutions.filter((i) =>
      ["Fed", "ECB", "CBRT"].includes(i),
    );
    if (!selected.length) {
      for (const [country, bank] of [
        ["USA", "Fed"],
        ["EA", "ECB"],
        ["TUR", "CBRT"],
      ])
        if (countries.includes(country)) selected.push(bank);
    }
    if (!selected.length)
      result.unresolved = "Specify which central bank's meeting you mean.";
    const year = filters.year ?? /\b((?:19|20)\d{2})\b/.exec(q)?.[1];
    const monthYear = new RegExp(
      `\\b(${monthNames})\\.?\\s+((?:19|20)\\d{2})\\b`,
    ).exec(q);
    const mdy = new RegExp(
      `\\b(${monthNames})\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?[,]?\\s+((?:19|20)\\d{2})\\b`,
    ).exec(q);
    const dmy = new RegExp(
      `\\b(\\d{1,2})\\s+(${monthNames})\\.?\\s+((?:19|20)\\d{2})\\b`,
    ).exec(q);
    const iso = /\b((?:19|20)\d{2}-\d{2}-\d{2})\b/.exec(q);
    const explicitDate =
      iso?.[1] ??
      (mdy
        ? `${mdy[3]}-${monthNumber(mdy[1])}-${mdy[2].padStart(2, "0")}`
        : dmy
          ? `${dmy[3]}-${monthNumber(dmy[2])}-${dmy[1].padStart(2, "0")}`
          : null);
    const explicitMonth = monthYear
      ? `${monthYear[2]}-${monthNumber(monthYear[1])}`
      : null;
    const anchorIndex =
      iso?.index ??
      mdy?.index ??
      dmy?.index ??
      monthYear?.index ??
      (year ? q.indexOf(year) : -1);
    const anchorPrefix = q.slice(0, anchorIndex);
    const bound = /\b(?:as of|by|before|prior to)\s*$/.test(anchorPrefix);
    const exclusive = /\b(?:before|prior to)\s*$/.test(anchorPrefix);
    const anchor =
      explicitDate ??
      (explicitMonth
        ? new Date(
            Date.UTC(
              Number(explicitMonth.slice(0, 4)),
              Number(explicitMonth.slice(5)),
              0,
            ),
          )
            .toISOString()
            .slice(0, 10)
        : year
          ? `${year}-12-31`
          : null);
    if (bound && anchor && anchor > result.asOf)
      result.unresolved = "That cutoff is beyond the reviewed corpus.";
    for (const institution of selected) {
      const dates = [
        ...new Set(
          reportMeetingCatalog.events
            .filter(
              (e) =>
                e.institution === institution &&
                e.publishedOn <= result.asOf &&
                (bound && anchor
                  ? exclusive
                    ? e.publishedOn < anchor
                    : e.publishedOn <= anchor
                  : explicitDate
                    ? e.date === explicitDate
                    : explicitMonth
                      ? e.date.startsWith(explicitMonth)
                      : !year || e.date.startsWith(year)) &&
                (!filters.publishedBy || e.publishedOn <= filters.publishedBy),
            )
            .map((e) => e.date),
        ),
      ]
        .sort()
        .reverse();
      const date = dates[previous && !exclusive ? 1 : 0];
      if (date) result.resolvedMeetings[institution] = date;
      else
        result.unresolved =
          "No verified meeting is available for that selection.";
    }
    // Choose the actual latest represented meeting first, regardless of whether
    // its minutes exist. Never replace missing latest minutes with older ones.
    return result;
  }
  const expressions = new RegExp(
    `\\b(?:(?<iso>(?:19|20)\\d{2}-\\d{2}-\\d{2})|(?<mdyMonth>${monthNames})\\.?\\s+(?<mdyDay>\\d{1,2})(?:st|nd|rd|th)?(?:,?\\s+(?<mdyYear>(?:19|20)\\d{2}))?|(?<dmyDay>\\d{1,2})\\s+(?<dmyMonth>${monthNames})\\.?(?:\\s+(?<dmyYear>(?:19|20)\\d{2}))?|(?<myMonth>${monthNames})\\.?\\s+(?<myYear>(?:19|20)\\d{2}))\\b`,
    "g",
  );
  const matches = [...q.matchAll(expressions)];
  const allYears = [...new Set(q.match(/\b(?:19|20)\d{2}\b/g) ?? [])];
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i],
      g = match.groups!;
    const start = match.index!,
      end = start + match[0].length;
    const before = q.slice(
      i ? matches[i - 1].index! + matches[i - 1][0].length : 0,
      start,
    );
    const after = q.slice(
      end,
      i + 1 < matches.length ? matches[i + 1].index : end + 50,
    );
    const directPublication =
      /\b(?:published|released|publication|available|yayimlanan|yayinlanan)\s+(?:on\s+|in\s+|by\s+)?$/.test(
        before,
      );
    const cutoff = /\b(?:before|prior to)\s+(?:the\s+)?$/.test(before);
    const directMeeting =
      /\b(?:meeting|toplantisi|toplanti)\s+(?:on\s+|in\s+|of\s+)?$/.test(
        before,
      ) ||
      /^\s*(?:(?:fomc|ecb|ppk|mpc)\s+)?(?:meeting|toplanti\w*)\b/.test(after);
    const publication =
      directPublication || cutoff || (!directMeeting && !eventIntent);
    const target = publication ? result.publication : result.event;
    if (!publication) result.eventRequired = true;
    const year =
      g.mdyYear ??
      g.dmyYear ??
      g.myYear ??
      (allYears.length === 1 ? allYears[0] : null);
    if (g.iso) target.date = g.iso;
    else if (g.myYear) target.month = `${g.myYear}-${monthNumber(g.myMonth)}`;
    else if (g.mdyMonth || g.dmyMonth) {
      const m = monthNumber(g.mdyMonth ?? g.dmyMonth),
        day = (g.mdyDay ?? g.dmyDay).padStart(2, "0");
      if (year) target.date = `${year}-${m}-${day}`;
      else {
        target.month = `????-${m}`;
        target.dayOfMonth = day;
        result.unresolved = "A year is needed to identify the requested date.";
      }
    }
    if (target.date) {
      const parsed = new Date(`${target.date}T00:00:00Z`);
      if (
        Number.isNaN(parsed.getTime()) ||
        parsed.toISOString().slice(0, 10) !== target.date
      )
        result.unresolved = "The requested date is invalid.";
    }
    if (cutoff && target.date) {
      result.publishedBefore = target.date;
      target.date = null;
    }
  }
  // Month/year without a day is preferred over a day-only interpretation.
  // The scanner's alternation is ordered to keep March2024 out of day parsing.
  if (!matches.length && allYears.length) {
    const target = eventIntent ? result.event : result.publication;
    target.years = allYears;
  }
  if (filters.year)
    (result.eventRequired ? result.event : result.publication).years = [
      filters.year,
    ];
  return result;
}

export function periodMatches(
  p: DatedPassage,
  period: EvidencePeriod,
): boolean {
  if (period.unresolved || p.publishedOn > period.asOf) return false;
  const matches = (date: string | null, c: DateConstraint) =>
    (!c.date || date === c.date) &&
    (!c.month || Boolean(date?.startsWith(c.month))) &&
    (!c.years.length || Boolean(date && c.years.includes(date.slice(0, 4))));
  const event = verifiedEvent(p);
  // A mixed OECD/Fed comparison applies its period to an OECD publication,
  // not an invented OECD meeting. Policy-bank event filters never fall back.
  const policyBank = ["Fed", "ECB", "CBRT"].includes(p.institution);
  const date = policyBank ? event.date : p.publishedOn;
  if (period.eventRequired && policyBank && !event.date) return false;
  if (
    !matches(date, period.event) ||
    !matches(p.publishedOn, period.publication)
  )
    return false;
  if (period.publishedBefore && p.publishedOn >= period.publishedBefore)
    return false;
  const resolved = period.resolvedMeetings[p.institution];
  return !resolved || (event.meeting && event.date === resolved);
}
