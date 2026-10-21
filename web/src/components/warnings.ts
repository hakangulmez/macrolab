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

export function warningTiers(checks: Check[]) {
  const blocking: Check[] = [];
  const important: Check[] = [];
  const notes: Check[] = [];
  const sources = new Map<string, SourceNoteGroup>();
  for (const check of checks) {
    // Severity wins over every presentation grouping, including source notes.
    if (check.level === "block") blocking.push(check);
    else if (check.level === "ok") continue;
    else if (check.code === "source_warning") {
      const key = `${check.country ?? ""}:${check.concept_id ?? ""}`;
      const group = sources.get(key) ?? {
        country: check.country,
        concept_id: check.concept_id,
        checks: [],
      };
      group.checks.push(check);
      sources.set(key, group);
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
