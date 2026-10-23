import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { Catalogue, Methods } from "../src/components/ReferenceScreens";
import { PublicationNotice } from "../src/components/PublicationNotice";
import type { CountryBundle, Manifest } from "../src/types";

const manifest: Manifest = {
  snapshot_id: "synthetic-vintage",
  as_of_date: "2026-10-21",
  countries: [
    {
      iso3: "USA",
      name: "Synthetic United States",
      latest_profiles: [
        {
          profile_id: "population",
          value: 1000,
          unit: "persons",
          date: "2024",
          source: "WorldBank",
        },
        {
          profile_id: "population",
          value: 1050,
          unit: "persons",
          date: "2025",
          source: "WorldBank",
        },
      ],
    },
    { iso3: "DEU", name: "Synthetic Germany" },
  ],
  indicators: [
    {
      concept_id: "gdp_real",
      title: "Real GDP",
      category: "Real activity",
      default_transform: "yoy_pct",
      frequency: "Q",
    },
  ],
  templates: [],
  schema_url: "/schema.json",
  sources: [
    {
      name: "OECD",
      terms_url: "https://www.oecd.org/en/about/terms-conditions.html",
      terms_status: "Dataset restrictions apply",
      attribution: "OECD synthetic fixture",
    },
  ],
  coverage: [
    {
      country: "USA",
      concept_id: "gdp_real",
      status: "available",
      first_date: "2000-Q1",
      last_date: "2026-Q2",
    },
    {
      country: "DEU",
      concept_id: "gdp_real",
      status: "missing",
      first_date: null,
      last_date: null,
    },
  ],
  models: [
    {
      id: "sing.ols",
      title: "Linear regression",
      family: "single_eq",
      summary: "Estimates association",
      label: "Association, not causation",
      assumptions: ["Conditional errors are orthogonal"],
      inputs: { min_series: 2, max_series: 6, frequencies: ["Q"] },
      params: {},
      references: [
        { title: "OLS reference", url: "https://www.statsmodels.org/" },
      ],
      runtime: "browser",
    },
  ],
  validation: {
    gate: "G2",
    code_version: "fixture",
    models: [
      {
        model_id: "sing.ols",
        reference_max_abs_difference: 2e-12,
        reference_tolerance: 1e-8,
        reference_outputs: { coefficients: 2e-12 },
        recovery: { coverage: 0.94, nominal_coverage: 0.95, repetitions: 100 },
      },
    ],
  },
};
const bundle: CountryBundle = {
  country: manifest.countries[0],
  snapshot_id: manifest.snapshot_id,
  profiles: [],
  series: {},
  cards: [
    {
      concept_id: "gdp_real",
      title: "Real GDP",
      definition: "Verified synthetic definition",
      default_transform: "yoy_pct",
      frequency: "Q",
      status: "limited",
      first_date: "2000-Q1",
      last_date: "2026-Q2",
      sources: ["OECD"],
      source_segments: [
        {
          source: "OECD",
          source_url: "https://sdmx.oecd.org/",
          unit: "IX",
          unit_label: "Index",
          sa_flag: "SA",
          definition: "Chain-linked volume index",
          attribution: "OECD fixture attribution",
          terms_status: "conditional",
          source_series_id: "SYNTHETIC",
          base_year: "2020",
        },
      ],
      flags: [],
      warnings: [],
      reason_codes: ["limited_history"],
      stale: false,
    },
  ],
};
const catalogue = (bundles: Record<string, CountryBundle> = { USA: bundle }) =>
  renderToStaticMarkup(
    <Catalogue
      manifest={manifest}
      countryBundles={bundles}
      loadCountry={vi.fn()}
    />,
  );

describe("Catalogue source fidelity", () => {
  it("renders the reviewed OECD and IMF citations verbatim with their source links", () => {
    for (const [source, citation, url] of [
      [
        "OECD",
        "OECD (2026), Quarterly National Accounts (database), accessed 21 October 2026.",
        "https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA/",
      ],
      [
        "IMF",
        "Source: International Monetary Fund, International Financial Statistics",
        "https://data.imf.org/en/datasets/IMF.STA:IFS",
      ],
    ]) {
      const attributed = {
        ...bundle,
        cards: bundle.cards.map((card) => ({
          ...card,
          sources: [source],
          source_segments: [{ source, attribution: citation, source_url: url }],
        })),
      };
      const html = catalogue({ USA: attributed });
      expect(html).toContain(citation);
      expect(html).toContain(`href="${url}"`);
    }
  });
  it("renders verified units, adjustment, dates, formula, attribution and reason", () => {
    const html = catalogue();
    for (const expected of [
      "Verified synthetic definition",
      "Index",
      "SA",
      "2000-Q1",
      "2026-Q2",
      "100 ×",
      "OECD fixture attribution",
      "limited history",
      "SYNTHETIC",
    ])
      expect(html).toContain(expected);
  });
  it("shows latest profile observations and marks country notes as drafts", () => {
    const html = catalogue();
    expect(html).toContain("1,050");
    expect(html).not.toContain("1,000");
    expect(html).toContain("Notes · DRAFT");
    expect(html).toContain("not included in models by default");
  });
  it("labels coverage status and both axes without relying on colour", () => {
    const html = catalogue();
    for (const expected of [
      'scope="col"',
      'scope="row"',
      "Synthetic Germany",
      "Available",
      "Missing",
      'aria-label="Scrollable country and indicator coverage matrix"',
    ])
      expect(html).toContain(expected);
  });
  it("does not present unloaded source metadata as observations", () => {
    const html = catalogue({});
    expect(html).toContain("Not loaded");
    expect(html).not.toContain("Verified synthetic definition");
    expect(html).toContain("Loading source metadata");
  });
  it("initializes the country, search and category from the Explore selection", () => {
    const html = renderToStaticMarkup(
      <Catalogue
        manifest={manifest}
        countryBundles={{}}
        loadCountry={vi.fn()}
        initialSelection={{
          country: "DEU",
          search: "GDP",
          category: "Real activity",
        }}
      />,
    );
    expect(html).toContain('<option value="DEU" selected="">');
    expect(html).toContain('value="GDP"');
    expect(html).toContain('<option value="Real activity" selected="">');
    expect(html).not.toContain("1,050");
  });
  it("resolves a region to its first actual country and falls back safely", () => {
    const grouped = {
      ...manifest,
      countries: manifest.countries.map((country) => ({
        ...country,
        region: country.iso3 === "DEU" ? "Europe" : "Americas",
      })),
    };
    const render = (region: string) =>
      renderToStaticMarkup(
        <Catalogue
          manifest={grouped}
          countryBundles={{}}
          loadCountry={vi.fn()}
          initialSelection={{ country: "unknown", region }}
        />,
      );
    expect(render("Europe")).toContain('<option value="DEU" selected="">');
    expect(render("unknown")).toContain('<option value="USA" selected="">');
  });
  it("opens the euro-area aggregate when its region is unspecified", () => {
    const html = renderToStaticMarkup(
      <Catalogue
        manifest={{
          ...manifest,
          countries: [...manifest.countries, { iso3: "EA", name: "Euro area" }],
        }}
        countryBundles={{}}
        loadCountry={vi.fn()}
        initialSelection={{ region: "Euro area" }}
      />,
    );
    expect(html).toContain('<option value="EA" selected="">');
  });
});

describe("Methods validation fidelity", () => {
  it("documents ratio severity and conditional exogenous diagnostics", () => {
    const html = renderToStaticMarkup(<Methods manifest={manifest} />);
    expect(html).toContain("Fewer than 5 produces an amber warning");
    expect(html).toContain("5 to below 10 produces a collapsed note");
    expect(html).toContain("10 or more produces no ratio message");
    expect(html).toContain(
      "Separate checks still block a model that cannot be estimated",
    );
    expect(html).toContain(
      "Stationarity findings for exogenous controls are notes",
    );
    expect(html).toContain("technical details and exports");
  });
  it("uses reported reference differences, coverage and model count", () => {
    const html = renderToStaticMarkup(<Methods manifest={manifest} />);
    for (const expected of [
      "1 / 1 models",
      "2.00e-12",
      "94%",
      "95%",
      "Conditional errors are orthogonal",
      "Dataset restrictions apply",
    ])
      expect(html).toContain(expected);
  });
  it("does not manufacture absent validation evidence", () => {
    const html = renderToStaticMarkup(
      <Methods manifest={{ ...manifest, validation: {} }} />,
    );
    expect(html).toContain("0 / 1 models");
    expect(html).toContain("Not reported");
    expect(html).not.toContain("94%");
    expect(html).toContain("not forecasts or automatic causal estimates");
  });
});

const candidate: Manifest = {
  ...manifest,
  countries: manifest.countries.map((country) => ({
    ...country,
    notes: [{ text: "Private unreviewed draft note" }],
    notes_status: "withheld_pending_review",
  })),
  publication: {
    mode: "static_candidate",
    approved: false,
    notes_withheld: true,
    excluded_sources: [
      {
        id: "wb",
        source: "World Bank",
        dataset: "Commodity prices",
        status: "unresolved",
        reason: "Redistribution terms unresolved",
      },
    ],
    excluded_observations: 400,
    policy_sha256: "fixture",
  },
};

describe("Static candidate provenance", () => {
  it("labels the all-source local comparison honestly and distinguishes Pink Sheet from WDI", () => {
    const local: Manifest = {
      ...candidate,
      publication: {
        ...candidate.publication!,
        source_mode: "all",
        local_only_comparison: true,
        excluded_observations: 0,
        excluded_sources: [
          {
            id: "pink",
            source: "WorldBank",
            dataset: "Commodity Price Data (Pink Sheet)",
            reason: "Third-party rights unresolved",
          },
        ],
      },
    };
    const notice = renderToStaticMarkup(<PublicationNotice manifest={local} />);
    expect(notice).toContain("Local comparison only");
    expect(notice).toContain("includes sources not cleared for publication");
    expect(notice).toContain("World Bank · Commodity Price Data (Pink Sheet)");
    expect(notice).not.toContain("are excluded under the source policy");
    const methods = renderToStaticMarkup(<Methods manifest={local} />);
    expect(methods).toContain(
      "All retrieved observations are retained for local comparison",
    );
    expect(methods).not.toContain(
      "observations were excluded from this candidate",
    );
    const cleared = renderToStaticMarkup(
      <PublicationNotice
        manifest={{
          ...local,
          publication: {
            ...local.publication!,
            source_mode: "cleared",
            local_only_comparison: false,
            excluded_observations: 400,
          },
        }}
      />,
    );
    expect(cleared).toBe("");
  });
  it("distinguishes withheld mapped sources from an unknown source mapping", () => {
    const withheld = {
      ...bundle,
      cards: bundle.cards.map((card) => ({
        ...card,
        status: "missing",
        sources: [],
        source_segments: [],
        reason_codes: [
          "no_verified_mapping_or_observations",
          "publication_source_excluded",
        ],
        flags: ["no_verified_mapping_or_observations"],
        warnings: ["no_verified_mapping_or_observations"],
        publication: {
          excluded_observations: 100,
          retained_observations: 0,
          excluded_sources: [
            {
              source: "WorldBank",
              dataset: "Pink Sheet",
              reason: "Third-party reuse remains unresolved.",
            },
          ],
        },
      })),
    };
    const html = renderToStaticMarkup(
      <Catalogue
        manifest={candidate}
        countryBundles={{ USA: withheld }}
        loadCountry={vi.fn()}
      />,
    );
    expect(html).toContain(
      "Mapped source data are excluded from this candidate",
    );
    expect(html).toContain("Third-party reuse remains unresolved");
    expect(html).toContain("WorldBank — not included");
    expect(html).toContain(
      "Source observations withheld under the publication policy",
    );
    expect(html).not.toContain("No mapped source");
    expect(html).not.toContain("no verified mapping or observations");
    expect(html).not.toContain("No verified source mapping is available");
  });
  it("keeps profile original-provider credits and licence links expandable", () => {
    const licensed = {
      ...candidate,
      countries: candidate.countries.map((country) => ({
        ...country,
        latest_profiles: [
          {
            profile_id: "population",
            value: 100,
            date: "2025",
            source: "WorldBank",
            source_series_id: "SP.POP.TOTL",
            source_url: "https://api.worldbank.org/v2/indicator/SP.POP.TOTL",
            attribution:
              "World Bank WDI; UN Population Division and national statistical offices.",
            terms_status: "allowed",
            terms_urls: [
              "https://creativecommons.org/licenses/by/4.0/",
              "https://data.worldbank.org/summary-terms-of-use",
            ],
            publication_restrictions: [
              "Credit original providers; no endorsement.",
            ],
          },
        ],
      })),
    };
    const html = renderToStaticMarkup(
      <Catalogue
        manifest={licensed}
        countryBundles={{ USA: bundle }}
        loadCountry={vi.fn()}
      />,
    );
    expect(html).toContain('<details data-testid="profile-source-details">');
    expect(html).toContain("Profile sources and licences");
    expect(html).toContain(
      "UN Population Division and national statistical offices",
    );
    expect(html).toContain(
      'href="https://creativecommons.org/licenses/by/4.0/"',
    );
    expect(html).toContain("Credit original providers; no endorsement");
  });
  it("shows a retained series' publication restrictions and source terms", () => {
    const licensedBundle = {
      ...bundle,
      cards: bundle.cards.map((card) => ({
        ...card,
        source_segments: card.source_segments.map((segment) => ({
          ...segment,
          terms_urls: ["https://data.bis.org/help/legal"],
          publication_restrictions: ["Credit BIS; do not imply endorsement."],
        })),
      })),
    };
    const html = renderToStaticMarkup(
      <Catalogue
        manifest={candidate}
        countryBundles={{ USA: licensedBundle }}
        loadCountry={vi.fn()}
      />,
    );
    expect(html).toContain("Reuse conditions");
    expect(html).toContain('href="https://data.bis.org/help/legal"');
    expect(html).toContain("Credit BIS; do not imply endorsement");
  });
  it("removes the candidate banner and puts the licensing note on About only", () => {
    const html = renderToStaticMarkup(
      <PublicationNotice manifest={candidate} openMethods={vi.fn()} />,
    );
    expect(html).toBe("");
    const about = renderToStaticMarkup(<Methods manifest={candidate} />);
    expect(about).toContain("Some sources are excluded for licensing reasons;");
    expect(about).toContain('href="#source-terms">see the data policy</a>.');
    expect(about).toContain("Country notes are withheld pending review");
    expect(
      renderToStaticMarkup(<PublicationNotice manifest={manifest} />),
    ).toBe("");
  });
  it("withholds unreviewed country notes and identifies excluded series observations", () => {
    const limited = {
      ...bundle,
      cards: bundle.cards.map((card) => ({
        ...card,
        publication: {
          excluded_observations: 400,
          retained_observations: 100,
          reason: "Redistribution terms unresolved",
        },
      })),
    };
    const html = renderToStaticMarkup(
      <Catalogue
        manifest={candidate}
        countryBundles={{ USA: limited }}
        loadCountry={vi.fn()}
      />,
    );
    expect(html).not.toContain("Private unreviewed draft note");
    expect(html).not.toContain("Notes · DRAFT");
    expect(html).toContain("Notes · Withheld");
    expect(html).toContain("Source data excluded from this candidate");
    expect(html).toContain("400 observations excluded");
    expect(html).toContain("100 retained");
  });
  it("presents the source policy and author without claiming deployment or permitting withheld data", () => {
    const html = renderToStaticMarkup(<Methods manifest={candidate} />);
    expect(html).toContain("About MacroLab");
    expect(html).toContain(
      "MacroLab is a non-commercial research and teaching tool.",
    );
    expect(html).toContain('href="https://hakangulmez.github.io/"');
    expect(html).toContain("Hakan Zeki Gülmez");
    expect(html).toContain("Excluded source records");
    expect(html).toContain("400 observations were excluded");
    expect(html).toContain("Redistribution terms unresolved");
  });
  it("explains a withheld commodity concept without implying that it is selectable or included", () => {
    const p2 = {
      ...candidate,
      publication: {
        ...candidate.publication!,
        included_global_factors: ["oil_brent", "us_policy_rate"],
        excluded_concepts: [
          {
            concept_id: "commod_idx",
            title: "Broad commodity index",
            reason:
              "Not included: Pink Sheet redistribution status remains unresolved.",
          },
        ],
      },
    };
    const html = renderToStaticMarkup(<Methods manifest={p2} />);
    expect(html).toContain('data-testid="excluded-concepts"');
    expect(html).toContain("Broad commodity index");
    expect(html).toContain(
      "Not included: Pink Sheet redistribution status remains unresolved.",
    );
    const comparison = renderToStaticMarkup(
      <PublicationNotice
        manifest={{
          ...p2,
          publication: { ...p2.publication, source_mode: "all" },
        }}
      />,
    );
    expect(comparison).not.toContain('data-testid="excluded-concepts"');
    expect(comparison).toContain("retains the full local snapshot");
  });
});
