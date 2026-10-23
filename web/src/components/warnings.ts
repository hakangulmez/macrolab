import type { Check, Country, Indicator } from "../types";

export const IMPORTANT_VISIBLE_LIMIT = 5;

const priority: Record<string, number> = {
  unstable_dynamics: 0,
  small_sample: 1,
  stale_input: 2,
  missing_coverage: 3,
  empty_common_sample: 3,
  model_fit_failed: 3,
  limited_coverage: 4,
  sample_fragmented: 5,
  collinearity: 6,
  shock_out_of_range: 7,
  nonstationary_level: 8,
};

const explanations: Record<string, string> = {
  publication_source_excluded:
    "source observations are withheld under the publication policy",
  internal_gaps: "some dates are missing",
  cross_country_adjustment_mismatch:
    "seasonal adjustment differs across countries",
  national_cpi_methodology:
    "consumer-price definitions follow national methods",
  unit_multiplier_not_reported: "the source does not report a unit multiplier",
  seasonal_adjustment_unknown: "seasonal adjustment is not reported",
  limited_history: "only a short history is available",
  stale: "the available history is old",
  source_discontinued: "the source series is no longer updated",
  composition_mismatch:
    "the aggregate's membership differs from the selected group",
  pre_euro_break: "the policy-rate definition changes at euro adoption",
  shared_rate: "the policy rate is shared across the euro area",
};

export interface SourceNoteGroup {
  country?: string;
  concept_id?: string;
  checks: Check[];
}

/** Presentation only: never replace the original checks in results or exports. */
export interface Finding extends Check {
  instances: Check[];
}

export function distinctFindings(checks: Check[]): Finding[] {
  const groups = new Map<string, Finding>();
  const severity = (check: Check) =>
    check.level === "block" ? 3 : check.level === "info" ? 1 : 2;
  for (const check of checks) {
    if (check.level === "ok") continue;
    const key = JSON.stringify([check.code, check.message]);
    const group = groups.get(key);
    if (!group) groups.set(key, { ...check, instances: [check] });
    else {
      group.instances.push(check);
      // A shared message must never hide a more serious instance.
      if (severity(check) > severity(group)) group.level = check.level;
    }
  }
  return [...groups.values()];
}

export function findingContext(
  finding: Finding,
  countries: Country[] = [],
  indicators: Indicator[] = [],
): string {
  const unique = (values: (string | undefined)[]) => [
    ...new Set(values.filter((value): value is string => Boolean(value))),
  ];
  const names = unique(finding.instances.map((c) => c.country)).map(
    (code) => countries.find((c) => c.iso3 === code)?.name ?? code,
  );
  const responses = unique(
    finding.instances.map(
      (c) =>
        c.concept_id ??
        (typeof c.response === "string" ? c.response : undefined),
    ),
  ).map(
    (id) =>
      indicators.find((i) => i.concept_id === id)?.title ??
      id.replaceAll("_", " "),
  );
  const horizons = [
    ...new Set(
      finding.instances.flatMap((c) =>
        typeof c.horizon === "number" && Number.isInteger(c.horizon)
          ? [c.horizon]
          : [],
      ),
    ),
  ].sort((a, b) => a - b);
  const ranges: string[] = [];
  for (let i = 0; i < horizons.length; i++) {
    const start = horizons[i];
    while (horizons[i + 1] === horizons[i] + 1) i++;
    ranges.push(
      start === horizons[i] ? String(start) : `${start}–${horizons[i]}`,
    );
  }
  return [
    names.join(", "),
    responses.join(", "),
    ranges.length
      ? `${horizons.length === 1 ? "horizon" : "horizons"} ${ranges.join(", ")}`
      : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function warningTiers(checks: Check[]) {
  const blocking: Finding[] = [];
  const important: Finding[] = [];
  const notes: Finding[] = [];
  const sourceFindings: Finding[] = [];
  const sources = new Map<string, SourceNoteGroup>();
  for (const check of distinctFindings(checks)) {
    // Severity wins over every presentation grouping, including source notes.
    if (check.level === "block") blocking.push(check);
    else if (check.level === "ok") continue;
    else if (check.code === "source_warning") {
      sourceFindings.push(check);
      for (const instance of check.instances) {
        const key = `${instance.country ?? ""}:${instance.concept_id ?? ""}`;
        const group = sources.get(key) ?? {
          country: instance.country,
          concept_id: instance.concept_id,
          checks: [],
        };
        group.checks.push(instance);
        sources.set(key, group);
      }
    } else if (check.level === "info") notes.push(check);
    else important.push(check); // Unknown/non-info severities must stay visible as important.
  }
  const ordered = important
    .map((check, index) => ({ check, index }))
    .sort(
      (a, b) =>
        (priority[a.check.code] ?? 20) - (priority[b.check.code] ?? 20) ||
        a.index - b.index,
    )
    .map(({ check }) => check);
  return {
    blocking,
    important: ordered.slice(0, IMPORTANT_VISIBLE_LIMIT),
    moreImportant: ordered.slice(IMPORTANT_VISIBLE_LIMIT),
    importantCount: ordered.length,
    notes,
    sourceFindings,
    sourceNotes: [...sources.values()],
  };
}

export function readableCheckMessage(
  check: Check,
  indicators: Indicator[] = [],
): string {
  let message = check.message;
  const replacements = {
    ...explanations,
    ...Object.fromEntries(
      indicators.map((indicator) => [indicator.concept_id, indicator.title]),
    ),
  };
  for (const [code, label] of Object.entries(replacements).sort(
    (a, b) => b[0].length - a[0].length,
  )) {
    const escaped = code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    message = message.replaceAll(new RegExp(`\\b${escaped}\\b`, "g"), label);
  }
  // Future reason codes still read as words; exact machine codes remain in details/export.
  return message.replace(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g, (value) =>
    value.replaceAll("_", " "),
  );
}

export function checkContext(
  check: Pick<Check, "country" | "concept_id">,
  countries: Country[] = [],
  indicators: Indicator[] = [],
): string {
  return [
    countries.find((country) => country.iso3 === check.country)?.name ??
      check.country,
    indicators.find((indicator) => indicator.concept_id === check.concept_id)
      ?.title ?? check.concept_id?.replaceAll("_", " "),
  ]
    .filter(Boolean)
    .join(" · ");
}

export function resultDisclosureChecks(
  checks: Check[],
  previouslyDisplayed?: Check[],
): Set<Check> {
  const identity = (check: Check) =>
    JSON.stringify([check.code, check.country ?? "", check.concept_id ?? ""]);
  const known =
    previouslyDisplayed && new Set(previouslyDisplayed.map(identity));
  return new Set(
    checks.filter(
      (check) =>
        check.phase === "post_estimation" ||
        (known !== undefined && !known.has(identity(check))),
    ),
  );
}
