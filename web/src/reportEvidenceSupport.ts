/** Conservative evidence checks. These never generate or paraphrase a claim. */
interface SupportRecord {
  text: string;
  country: string;
  institution: string;
  section: string | null;
  kind: string;
}
export interface EvidenceSupport {
  supported: boolean;
  reasons: string[];
}
const topics: [string, RegExp, RegExp][] = [
  [
    "inflation",
    /\b(?:inflation|cpi|hicp|deflation|consumer prices?)\b/i,
    /\b(?:inflation\w*|cpi|hicp|deflation|prices?)\b/i,
  ],
  [
    "activity",
    /\b(?:gdp|output|growth|recession)\b/i,
    /\b(?:gdp|output|growth|recession|activity|expand\w*|contract\w*)\b/i,
  ],
  [
    "labour",
    /\b(?:unemployment|employment|labor|labour|jobs?|payrolls?)\b/i,
    /\b(?:unemployment|employment|labor|labour|jobs?|payrolls?|hiring)\b/i,
  ],
  [
    "credit",
    /\b(?:lending|loan|credit)\b/i,
    /\b(?:lending|loans?|credit|banks?)\b/i,
  ],
  [
    "assets",
    /\b(?:purchases?|purchasing|treasur\w*|mbs|mortgage|pepp|app|asset)\b/i,
    /\b(?:purchas\w*|treasur\w*|mbs|mortgage|pepp|app|securit\w*|asset)\b/i,
  ],
];
const increase =
  /\b(?:rais(?:e|es|ed|ing)|increas\w*|hike\w*|higher|ris(?:e|es|en|ing)|tighten\w*|artir\w*)\b/i;
const decrease =
  /\b(?:cut\w*|lower\w*|reduc\w*|decreas\w*|declin\w*|fall\w*|fell|eas\w*|indiri\w*)\b/i;
const hold =
  /\b(?:maintain\w*|unchanged|hold|held|keep|kept|retain\w*|sabit)\b/i;
const forecast =
  /\b(?:forecast\w*|project\w*|expect(?:s|ed|ing)?|intend\w*|plan\w* to|likely|will|would|could|may|might|anticipat\w*|(?:is|are) set to)\b/i;
const recommendation = /\b(?:should|recommend\w*|need\w* to|ought to)\b/i;
const actualDecision =
  /\b(?:decid\w*|agreed|announced|voted|set|maintain\w*|raised|reduced|lowered|cut|increased)\b/i;

function normalize(value: string): string {
  return value
    .replace(/(\d*)([¼½¾⅛⅜⅝⅞])/g, (_, whole: string, fraction: string) =>
      String(
        Number(whole || 0) +
          ({
            "¼": 0.25,
            "½": 0.5,
            "¾": 0.75,
            "⅛": 0.125,
            "⅜": 0.375,
            "⅝": 0.625,
            "⅞": 0.875,
          }[fraction] ?? 0),
      ),
    )
    .normalize("NFKC")
    .replace(/[’‘]/g, "'")
    .replace(/(\d+)[-–](\d+)\/(\d+)/g, (_, a, b, c) =>
      String(Number(a) + Number(b) / Number(c)),
    )
    .replace(/\b(\d+)\/(\d+)\b/g, (_, a, b) => String(Number(a) / Number(b)))
    .replace(/three[- ]quarters?/gi, "0.75")
    .replace(/one[- ]half|a half|half/gi, "0.5")
    .replace(/one[- ]quarter|a quarter|quarter/gi, "0.25")
    .replace(/[-–](?=percentage|point|basis)/gi, " ")
    .toLowerCase();
}
interface Quantity {
  value: number;
  unit: string;
  role: "by" | "to" | null;
}
function quantities(text: string): Quantity[] {
  const s = normalize(text),
    values: Quantity[] = [];
  const re =
    /(?:[$€£]\s*)?(\d+(?:\.\d+)?)\s*(basis points?|bps?\b|percentage points?|percent\b|%|billion\b|trillion\b)/gi;
  for (const m of s.matchAll(re)) {
    const n = Number(m[1]),
      u = m[2];
    const before = s.slice(Math.max(0, m.index! - 35), m.index!);
    const role =
      /\b(?:by|additional|an additional|of an additional)\s*[$€£]?\s*$/.test(
        before,
      )
        ? "by"
        : /\b(?:to|(?:a )?total(?: envelope)?(?: of| at)?|envelope at)\s*[$€£]?\s*$/.test(
              before,
            )
          ? "to"
          : null;
    values.push({
      value: /percentage/.test(u) ? n * 100 : /trillion/.test(u) ? n * 1000 : n,
      unit: /basis|bps?\b|percentage/.test(u)
        ? "bp"
        : /billion|trillion/.test(u)
          ? "billion"
          : "percent",
      role,
    });
  }
  for (const m of s.matchAll(
    /\b(\d+(?:\.\d+)?)\s+(?:to|and|[-–])\s+(\d+(?:\.\d+)?)\s*(?:percent|%)/g,
  ))
    values.push({ value: Number(m[1]), unit: "percent", role: "to" });
  return values;
}
function sentences(text: string): string[] {
  // Initials must not split an attribution such as "Michelle W. Bowman".
  return text.replace(/\b([A-Z])\.\s/g, "$1 ").split(/(?<=[.!?;])\s+(?=[A-Z])/);
}
function assertedAction(
  question: string,
): "increase" | "decrease" | "hold" | null {
  // A nominal head asserts a direction just as a finite verb does.
  const nominal =
    /^\s*(?:what|which)\s+(increase|hike|reduction|decrease|cut)\b/i.exec(
      question,
    );
  if (nominal) return increase.test(nominal[1]) ? "increase" : "decrease";
  const m = /\b(?:did|does|has|had)\b([\s\S]*)/i.exec(question);
  if (!m) {
    if (/\b(?:rationale|reasons?)\b.*\b(?:for|behind)\b/i.test(question))
      return increase.test(question)
        ? "increase"
        : decrease.test(question)
          ? "decrease"
          : null;
    return null;
  }
  if (/\brecommend\w*\b/i.test(m[1]))
    return increase.test(m[1])
      ? "increase"
      : decrease.test(m[1])
        ? "decrease"
        : null;
  const action =
    /\b(?:raise|raised|increase|increased|hike|hiked|tighten|tightened|cut|lower|lowered|reduce|reduced|decrease|decreased|maintain|maintained|hold|held|keep|kept|retain|retained)\b/i.exec(
      m[1],
    );
  if (
    !action ||
    /\b(?:before|until|could|might|may|would|confidence|if|whether|what|which)\b/i.test(
      m[1].slice(0, action.index),
    )
  )
    return null;
  return increase.test(action[0])
    ? "increase"
    : decrease.test(action[0])
      ? "decrease"
      : "hold";
}
function namedActor(question: string): string | null {
  const m =
    /\b(?:did|does|has|had)\s+([A-Z][a-z]+(?:\s+[A-Z]\.)?\s+[A-Z][a-z]+)\s+(?:prefer|vote|support|oppose|decide|recommend)/.exec(
      question,
    );
  return m &&
    !/Governing Council|Federal Reserve|European Central|Monetary Policy/.test(
      m[1],
    )
    ? m[1].split(/\s+/).at(-1)!.toLowerCase()
    : null;
}

export function checkEvidenceSupport(
  question: string,
  leading: SupportRecord,
  context: SupportRecord[] = [leading],
): EvidenceSupport {
  const reasons: string[] = [],
    q = normalize(question);
  const body = context.map((p) => p.text).join(" ");
  // Preserve explicit predicate negation; lexical overlap cannot prove its opposite.
  for (const match of normalize(body).matchAll(
    /\bnot\s+(on\s+(?:a|an|the)\s+[\w-]+\s+[\w-]+)\b/g,
  )) {
    const predicate = match[1];
    if (q.includes(predicate) && !q.includes(`not ${predicate}`))
      reasons.push("contradicted_predicate_polarity");
  }
  const selectedTopics = topics.filter(([, query]) => query.test(question));
  for (const [name, , source] of selectedTopics)
    if (!source.test(body)) reasons.push(`missing_${name}_evidence`);
  const rateQuestion =
    /\b(?:policy rate|interest rate|target range|funds rate|bank rate|deposit facility|refinancing|faiz)\b/i.test(
      question,
    ) ||
    (/\brates?\b/.test(q) &&
      !/\b(?:inflation|unemployment|growth) rate\b/.test(q));
  if (rateQuestion && !/\b(?:rates?|target range|faiz|repo)\b/i.test(body))
    reasons.push("missing_rate_evidence");

  const actor = namedActor(question);
  let clauses = context.flatMap((p) => sentences(p.text));
  if (selectedTopics.length === 1 && !rateQuestion)
    clauses = clauses.filter((s) => selectedTopics[0][2].test(s));
  if (actor)
    clauses = clauses.filter((s) => new RegExp(`\\b${actor}\\b`, "i").test(s));
  if (actor && !clauses.length) reasons.push("missing_named_actor");
  const policy = ["Fed", "ECB", "CBRT"].includes(leading.institution);
  if (
    policy &&
    /\b(?:decid\w*|decision|announc\w*|agree\w*|PPK)\b|karar/i.test(question) &&
    !/\b(?:decid\w*|agreed|announc\w*|vot\w*|intends? to|plans? to|rates?\s+(?:unchanged|remain)|(?:will|shall)\s+(?:continue|increase|reduce|lower|purchase|conclude)|to conduct interventions)\b/i.test(
      leading.text,
    )
  )
    reasons.push("missing_decision_evidence_in_leading_passage");
  if (!actor && policy && rateQuestion) {
    clauses = clauses.filter(
      (s) =>
        /\b(?:policy rate|interest rates?|funds rate|repo|target range|bank rate|deposit facility)\b/i.test(
          s,
        ) &&
        !/\b(?:voting against|preferred|opposed|survey respondents|market.implied)\b/i.test(
          s,
        ),
    );
  }
  const instrument =
    /\btreasur\w*\b/i.test(question) && !/\b(?:mbs|mortgage)\b/i.test(question)
      ? /\btreasur\w*\b/i
      : /\b(?:mbs|mortgage)\b/i.test(question) &&
          !/\btreasur\w*\b/i.test(question)
        ? /\b(?:mbs|mortgage)\b/i
        : null;
  if (instrument) clauses = clauses.filter((s) => instrument.test(s));
  // A number in another instrument's paragraph, or a dissenting member's
  // preference, cannot establish the adopted policy decision's amount.
  const action = assertedAction(question);
  if (action) {
    const test =
      action === "increase"
        ? increase
        : action === "decrease"
          ? decrease
          : hold;
    clauses = clauses.filter(
      (s) =>
        test.test(s) &&
        !/\b(?:not|never)\s+(?:\w+\s+){0,2}(?:raise|increase|cut|lower|reduce)\b/i.test(
          s,
        ),
    );
    if (!clauses.length) reasons.push("unverified_action");
  }
  const asserted =
    (/^(?:why|how|when)\b/i.test(question.trim()) &&
      /\b(?:did|does|has|had|was|were)\b/i.test(question)) ||
    /\b(?:rationale|observed|recorded|already)\b/i.test(question) ||
    (Boolean(action) && quantities(question).length > 0);
  const values = quantities(question);
  if (asserted && values.length) {
    const source = clauses.flatMap(quantities);
    for (const v of values)
      if (
        !source.some(
          (x) =>
            x.unit === v.unit &&
            Math.abs(x.value - v.value) < 1e-8 &&
            (!v.role || !x.role || v.role === x.role),
        )
      )
        reasons.push("unverified_amount_or_role");
    // Finding both numbers in a Treasury+MBS paragraph does not verify a swap.
    const instruments = [
      /\btreasur\w*\b/i,
      /\b(?:mortgage|mbs)\b/i,
      /\bagency debt\b/i,
    ];
    for (const instrument of instruments) {
      const queryParts = question
        .split(/\s+(?:and|while|whereas|but)\s+/i)
        .filter((s) => instrument.test(s));
      for (const part of queryParts) {
        const wanted = quantities(part);
        if (!wanted.length) continue;
        const sourceParts = clauses
          .flatMap((s) => s.split(/\s+(?:and|while|whereas|but)\s+/i))
          .filter((s) => instrument.test(s))
          .flatMap(quantities);
        if (
          wanted.some(
            (v) =>
              !sourceParts.some(
                (x) =>
                  x.unit === v.unit &&
                  Math.abs(x.value - v.value) < 1e-8 &&
                  (!v.role || !x.role || v.role === x.role),
              ),
          )
        )
          reasons.push("unverified_instrument_amount_pair");
      }
    }
  }
  if (asserted) {
    for (const word of [
      "earlier",
      "later",
      "smaller",
      "larger",
      "upside",
      "downside",
      "above",
      "below",
      "upward",
      "downward",
    ])
      if (
        new RegExp(`\\b${word}\\b`).test(q) &&
        !new RegExp(`\\b${word}\\b`, "i").test(clauses.join(" "))
      )
        reasons.push("unverified_comparison");
    for (const [, query, source] of selectedTopics) {
      const requested = question
        .split(/\s+(?:and|while|whereas|but)\s+/i)
        .filter((s) => query.test(s));
      const original = clauses
        .flatMap((s) => s.split(/\s+(?:and|while|whereas|but)\s+/i))
        .filter((s) => source.test(s))
        .join(" ");
      for (const part of requested)
        for (const word of [
          "upside",
          "downside",
          "above",
          "below",
          "upward",
          "downward",
        ])
          if (
            new RegExp(`\\b${word}\\b`, "i").test(part) &&
            !new RegExp(`\\b${word}\\b`, "i").test(original)
          )
            reasons.push("unverified_variable_direction_pair");
    }
    const asksForecast =
      forecast.test(question) || recommendation.test(question);
    const observed =
      /\b(?:already|observed|recorded|realised|realized|purchased|bought|implemented|occurred|had|fell|was|were)\b/i.test(
        question,
      ) ||
      (action && !asksForecast);
    if (
      observed &&
      clauses.length &&
      clauses.every((s) => forecast.test(s) || recommendation.test(s)) &&
      !clauses.some((s) => actualDecision.test(s) && !forecast.test(s))
    )
      reasons.push("forecast_or_recommendation_is_not_observation");
    if (
      /\bstaff\b/i.test(question) &&
      !/\bstaff\b/i.test(body + " " + (leading.section ?? ""))
    )
      reasons.push("unverified_staff_attribution");
  }
  return { supported: reasons.length === 0, reasons: [...new Set(reasons)] };
}
