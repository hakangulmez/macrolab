import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Checks } from "../src/components/Common";
import {
  checkContext,
  distinctFindings,
  findingContext,
  readableCheckMessage,
  warningTiers,
} from "../src/components/warnings";
import type { Check } from "../src/types";

const warning = (
  code: string,
  level = "warn",
  extra: Partial<Check> = {},
): Check => ({
  code,
  level,
  message: `A ${code} condition.`,
  ...extra,
});

describe("Warning tiers", () => {
  it("groups identical findings across countries, responses and horizons without losing instances", () => {
    const checks = ["DEU", "FRA", "ITA", "ESP"].flatMap((country) =>
      ["gdp_real", "cpi", "unemp"].flatMap((response) =>
        Array.from({ length: 13 }, (_, horizon) =>
          warning("small_sample", "warn", {
            country,
            response,
            horizon,
            nobs: 90 - horizon,
            message: "Fewer than five observations per parameter.",
          }),
        ),
      ),
    );
    const snapshot = structuredClone(checks);
    const groups = distinctFindings(checks);
    expect(groups).toHaveLength(1);
    expect(groups[0].instances).toEqual(snapshot);
    expect(
      findingContext(
        groups[0],
        [
          { iso3: "DEU", name: "Germany" },
          { iso3: "FRA", name: "France" },
          { iso3: "ITA", name: "Italy" },
          { iso3: "ESP", name: "Spain" },
        ],
        [{ concept_id: "cpi", title: "HICP" }],
      ),
    ).toBe(
      "Germany, France, Italy, Spain · gdp real, HICP, unemp · horizons 0–12",
    );
    const html = renderToStaticMarkup(<Checks checks={checks} />);
    expect(html).toContain("Important · 1");
    expect(html.match(/&quot;nobs&quot;/g)).toHaveLength(156);
    expect(checks).toEqual(snapshot);
  });

  it("keeps distinct messages separate, preserves sparse horizons, and promotes shared blockers", () => {
    const checks = [
      warning("a", "info", { horizon: 0 }),
      warning("a", "warn", { horizon: 2 }),
      warning("a", "block", { horizon: 3 }),
      warning("a", "warn", { message: "Different finding" }),
      warning("b", "info", { message: "Different finding" }),
    ];
    const tiers = warningTiers(checks);
    expect(tiers.blocking).toHaveLength(1);
    expect(tiers.blocking[0].instances).toEqual(checks.slice(0, 3));
    expect(findingContext(tiers.blocking[0])).toBe("horizons 0, 2–3");
    expect(tiers.importantCount).toBe(1);
    expect(tiers.notes).toHaveLength(1);
  });
  it("marks only new disclosures when Builder coverage expands into five Results warnings", () => {
    const before = ["cpi", "unemp"].map((concept_id) =>
      warning("limited_coverage", "warn", {
        concept_id,
        country: "USA",
        phase: "preflight",
      }),
    );
    const after = [
      ...before.map((check) => ({
        ...check,
        phase: "pre_estimation" as const,
        message: "Full prepared-data coverage details.",
      })),
      ...["gdp_real", "unemp", "policy_rate"].map((concept_id) =>
        warning("nonstationary_level", "warn", {
          concept_id,
          country: "USA",
          phase: "pre_estimation",
        }),
      ),
    ];
    const html = renderToStaticMarkup(
      <Checks
        checks={after}
        showEstimationPhase
        previouslyDisplayedChecks={before}
      />,
    );
    expect(html).toContain("Important · 2");
    expect(html.match(/Found after estimation/g)).toHaveLength(1);
    expect(html).toContain("pre_estimation");
    const compatibilityKnown = renderToStaticMarkup(
      <Checks
        checks={after}
        showEstimationPhase
        previouslyDisplayedChecks={after}
      />,
    );
    expect(compatibilityKnown).not.toContain("Found after estimation");
    expect(compatibilityKnown).toContain("Important · 2");
  });

  it("matches disclosure identity by country and concept, while fitted checks always carry the label", () => {
    const known = warning("limited_coverage", "warn", {
      country: "USA",
      concept_id: "cpi",
      phase: "preflight",
    });
    const fitted = warning("small_sample", "info", {
      country: "USA",
      phase: "post_estimation",
    });
    const html = renderToStaticMarkup(
      <Checks
        checks={[
          { ...known, country: "GBR" },
          { ...known, concept_id: "unemp" },
          fitted,
        ]}
        showEstimationPhase
        previouslyDisplayedChecks={[known, fitted]}
      />,
    );
    expect(html.match(/Found after estimation/g)).toHaveLength(2);
  });
  it("labels fitted checks in Results without mislabelling prepared-data diagnostics", () => {
    const checks = [
      warning("small_sample", "info", { phase: "post_estimation" }),
      warning("unstable_dynamics", "warn", { phase: "post_estimation" }),
      warning("nonstationary_level", "info", {
        phase: "pre_estimation",
        role: "exogenous",
      }),
    ];
    const tiers = warningTiers(checks);
    expect(tiers.notes).toHaveLength(2);
    expect(tiers.importantCount).toBe(1);
    const html = renderToStaticMarkup(
      <Checks checks={checks} showEstimationPhase />,
    );
    expect(html.match(/Found after estimation/g)).toHaveLength(2);
    expect(html).toContain("Builder checks coverage first");
    expect(html).toContain("post_estimation");
    const builder = renderToStaticMarkup(<Checks checks={checks} />);
    expect(builder).not.toContain("Found after estimation");
  });
  it("keeps every blocker visible, including a source-coded failure", () => {
    const blockers = Array.from({ length: 8 }, (_, index) =>
      warning(`failure_${index}`, "block"),
    );
    blockers.push(warning("source_warning", "block"));
    const tiers = warningTiers([
      ...blockers,
      warning("source_warning", "warn", { country: "USA", concept_id: "cpi" }),
    ]);
    expect(
      tiers.blocking.map((finding) => {
        const check: Partial<typeof finding> = { ...finding };
        delete check.instances;
        return check;
      }),
    ).toEqual(blockers);
    expect(tiers.blocking.at(-1)?.instances).toHaveLength(2);
    expect(tiers.sourceNotes).toHaveLength(0);
    const html = renderToStaticMarkup(<Checks checks={blockers} />);
    expect(html).toContain('aria-label="Blocking checks"');
    expect(html).toContain("Blocking · 9");
    expect(html).not.toContain("more important warnings");
  });
  it("prioritizes instability, sample size and data problems and caps only the initial important list", () => {
    const checks = [
      "shared_rate",
      "elb_period",
      "nonstationary_level",
      "limited_coverage",
      "missing_coverage",
      "stale_input",
      "small_sample",
      "unstable_dynamics",
    ].map((code) => warning(code));
    const snapshot = structuredClone(checks);
    const tiers = warningTiers(checks);
    expect(tiers.important.map((check) => check.code)).toEqual([
      "unstable_dynamics",
      "small_sample",
      "stale_input",
      "missing_coverage",
      "limited_coverage",
    ]);
    expect(tiers.moreImportant).toHaveLength(3);
    expect(tiers.notes).toHaveLength(0);
    expect(checks).toEqual(snapshot);
    const html = renderToStaticMarkup(<Checks checks={checks} />);
    expect(html).toContain("Important · 8");
    expect(html).toContain("3 more important warnings");
    expect(html).not.toContain("source notes");
  });
  it("deduplicates source series while retaining every original source record", () => {
    const source = warning("source_warning", "warn", {
      country: "USA",
      concept_id: "cpi",
      flags: ["internal_gaps"],
    });
    const tiers = warningTiers([
      source,
      { ...source, flags: ["national_cpi_methodology"] },
      { ...source, country: "DEU" },
      warning("covid_period", "info"),
      warning("valid", "ok"),
    ]);
    expect(tiers.sourceNotes).toHaveLength(2);
    expect(tiers.sourceNotes[0].checks).toHaveLength(2);
    expect(tiers.notes).toHaveLength(1);
    expect(tiers.importantCount).toBe(0);
    const html = renderToStaticMarkup(
      <Checks checks={[source, source]} onSourceCard={vi.fn()} />,
    );
    expect(html).toContain('<details class="warning-tier warning-notes">');
    expect(html).toContain("1 source notes");
    expect(html).toContain("1 series has");
    expect(html).toContain('class="source-note-links"');
    expect(html).toContain("USA · cpi");
    expect(html).toContain("Technical details");
  });
  it("does not demote unknown warning severities or failed checks to notes", () => {
    const tiers = warningTiers([
      warning("future_failure", "error"),
      warning("model_fit_failed"),
      warning("stationarity_inconclusive", "info"),
    ]);
    expect(tiers.important.map((check) => check.code)).toEqual([
      "model_fit_failed",
      "future_failure",
    ]);
    expect(tiers.notes[0].code).toBe("stationarity_inconclusive");
  });
});

describe("Readable warning messages", () => {
  it("translates source reason codes without dropping the data limitation", () => {
    const check = warning("limited_coverage", "warn", {
      message:
        "cpi has data limits: internal_gaps, cross_country_adjustment_mismatch, national_cpi_methodology, unit_multiplier_not_reported.",
      concept_id: "cpi",
    });
    const message = readableCheckMessage(check, [
      { concept_id: "cpi", title: "Consumer prices" },
    ]);
    expect(message).toContain("Consumer prices has data limits");
    expect(message).toContain("some dates are missing");
    expect(message).toContain("seasonal adjustment differs across countries");
    expect(message).toContain("national methods");
    expect(message).toContain("does not report a unit multiplier");
    expect(message).not.toContain("_");
    expect(check.message).toContain("internal_gaps");
  });
  it("keeps unknown reasons readable and avoids replacing a partial code or ordinary word", () => {
    expect(
      readableCheckMessage(
        warning("limited_coverage", "warn", {
          message: "staleness and cpi_core have new_source_caveat",
          concept_id: "cpi_core",
        }),
        [{ concept_id: "cpi", title: "Prices" }],
      ),
    ).toBe("staleness and cpi core have new source caveat");
  });
  it("resolves country and indicator context without machine identifiers", () => {
    expect(
      checkContext(
        { country: "DEU", concept_id: "policy_rate" },
        [{ iso3: "DEU", name: "Germany" }],
        [{ concept_id: "policy_rate", title: "Policy rate" }],
      ),
    ).toBe("Germany · Policy rate");
    expect(checkContext({ concept_id: "future_series" })).toBe("future series");
  });
  it("retains fixes and machine records in expanded technical details only", () => {
    const check = warning("missing_coverage", "block", {
      country: "USA",
      concept_id: "gdp_real",
      message: "No data for gdp_real.",
      fix: { remove_series: "gdp_real" },
    });
    const html = renderToStaticMarkup(
      <Checks checks={[check]} onFix={vi.fn()} onSourceCard={vi.fn()} />,
    );
    expect(html).toContain("No data for gdp real.");
    expect(html).toContain("Apply suggested change");
    expect(html).toContain("View series card");
    const visible = html.replace(/<details\b[^>]*>[\s\S]*?<\/details>/g, "");
    expect(visible).not.toContain("missing_coverage");
    expect(visible).not.toContain("gdp_real");
    expect(html).toContain("missing_coverage");
  });
});
