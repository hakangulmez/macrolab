import { buildVersion, snapshotDate } from "../version";
import { countryIndicators } from "../displayLabels";
import { useEffect, useMemo, useState } from "react";
import type { CountryBundle, JsonRecord, Manifest } from "../types";
import {
  formulas,
  indicatorSummary,
  number,
  record,
  records,
  strings,
  text,
  transforms,
} from "../format";
import { Field, Status } from "./Common";

interface CatalogueProps {
  manifest: Manifest;
  countryBundles: Record<string, CountryBundle>;
  loadCountry: (iso: string) => void;
  initialSelection?: {
    country?: string;
    search?: string;
    category?: string;
    region?: string;
  };
}

const profileLabels: Record<string, string> = {
  population: "Population",
  gdp_per_capita_ppp: "GDP per person, PPP",
  trade_openness: "Trade openness",
  research_development: "Research & development",
  rd_gdp: "Research & development",
  age_dependency: "Age dependency",
};

function SourceLink({ url, children }: { url: unknown; children: string }) {
  return typeof url === "string" && /^https:\/\//.test(url) ? (
    <a href={url} target="_blank" rel="noreferrer">
      {children}
    </a>
  ) : (
    <span>{children}</span>
  );
}

function latestProfiles(rows: JsonRecord[]): JsonRecord[] {
  const latest = new Map<string, JsonRecord>();
  for (const row of rows) {
    const id = text(row.profile_id, "");
    if (id && (!latest.has(id) || text(row.date) > text(latest.get(id)?.date)))
      latest.set(id, row);
  }
  return [...latest.values()];
}

export function Catalogue({
  manifest,
  countryBundles,
  loadCountry,
  initialSelection,
}: CatalogueProps) {
  const [country, setCountry] = useState(
    () =>
      manifest.countries.find((c) => c.iso3 === initialSelection?.country)
        ?.iso3 ??
      (initialSelection?.region
        ? manifest.countries.find(
            (c) =>
              c.region === initialSelection.region ||
              (initialSelection.region === "Euro area" && c.iso3 === "EA"),
          )?.iso3
        : undefined) ??
      manifest.countries.find((c) => c.iso3 === "USA")?.iso3 ??
      manifest.countries[0]?.iso3 ??
      "",
  );
  const [search, setSearch] = useState(initialSelection?.search ?? "");
  const [category, setCategory] = useState(initialSelection?.category ?? "all");
  const [page, setPage] = useState(0);
  const bundle = countryBundles[country];
  useEffect(() => {
    if (country && !bundle) loadCountry(country);
  }, [country, bundle, loadCountry]);
  const countryMetadata = manifest.countries.find((c) => c.iso3 === country);
  const countryName = countryMetadata?.name ?? country;
  const notesWithheld =
    manifest.publication?.notes_withheld === true ||
    countryMetadata?.notes_status === "withheld_pending_review";
  const groups = [
    ...new Set(
      manifest.indicators
        .map((i) => i.category)
        .filter((s): s is string => Boolean(s)),
    ),
  ];
  const filtered = countryIndicators(manifest.indicators, country).filter(
    (i) =>
      (category === "all" || i.category === category) &&
      `${i.title} ${i.concept_id} ${i.definition ?? ""}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / 6));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(currentPage * 6, (currentPage + 1) * 6);
  const profiles = latestProfiles(
    records(countryMetadata?.latest_profiles).length
      ? records(countryMetadata?.latest_profiles)
      : records(bundle?.profiles),
  );
  const coverage = useMemo(
    () =>
      new Map(
        records(manifest.coverage).map((row) => [
          `${text(row.country)}:${text(row.concept_id)}`,
          row,
        ]),
      ),
    [manifest.coverage],
  );

  return (
    <div className="stack">
      <header className="page-heading">
        <div className="overline">Data & provenance</div>
        <h1>Data catalogue</h1>
        <p>
          See what is available, how each series is measured, and which source
          supports it. Missing observations stay missing.
        </p>
        <p className="small muted">{indicatorSummary(manifest)}</p>
      </header>
      <section className="card stack" aria-labelledby="catalogue-filters">
        <h2 id="catalogue-filters">Find an indicator</h2>
        <div className="triple-grid">
          <Field label="Country">
            <select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
            >
              {manifest.countries.map((c) => (
                <option key={c.iso3} value={c.iso3}>
                  {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Search indicators">
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              placeholder="GDP, prices, policy rate…"
            />
          </Field>
          <Field label="Indicator category">
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(0);
              }}
            >
              <option value="all">All categories</option>
              {groups.map((group) => (
                <option key={group} value={group}>
                  {group}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <p className="small muted">
          {filtered.length} catalogue entries match · Snapshot{" "}
          {manifest.snapshot_id} · As of {manifest.as_of_date}
        </p>
      </section>

      <section className="card stack" aria-labelledby="country-profile">
        <div className="row between">
          <h2 id="country-profile">{countryName}: country profile</h2>
          <span className="badge draft">
            {notesWithheld ? "Notes · Withheld" : "Notes · DRAFT"}
          </span>
        </div>
        <p className="small muted">
          Latest reported annual values. Structural profiles provide context and
          are not included in models by default.
        </p>
        {profiles.length ? (
          <div className="profile-grid">
            {profiles.map((profile) => (
              <div key={text(profile.profile_id)}>
                <span>
                  {profileLabels[text(profile.profile_id)] ??
                    text(profile.indicator_title, text(profile.profile_id))}
                </span>
                <strong>
                  {number(
                    profile.value,
                    text(profile.profile_id) === "population" ? 0 : 2,
                  )}
                </strong>
                <span>
                  {text(profile.unit)} · {text(profile.date)}
                </span>
                <SourceLink
                  url={profile.source_url}
                  children={text(profile.source, "Source")}
                />
              </div>
            ))}
          </div>
        ) : (
          <p className="small">
            No structural profile observations are reported for this unit.
          </p>
        )}
        {profiles.length > 0 && (
          <details data-testid="profile-source-details">
            <summary>Profile sources and licences</summary>
            <ul className="source-list">
              {profiles.map((profile) => (
                <li key={text(profile.profile_id)} className="stack small">
                  <strong>
                    {profileLabels[text(profile.profile_id)] ??
                      text(profile.indicator_title, text(profile.profile_id))}
                  </strong>
                  <p>
                    {text(
                      profile.attribution,
                      "Attribution is not reported in this snapshot.",
                    )}
                  </p>
                  <SourceLink
                    url={profile.source_url}
                    children={`${text(profile.source, "Source")} · ${text(profile.source_series_id, "source record")}`}
                  />
                  <p>
                    {text(
                      profile.terms_status,
                      "Reuse status is not reported.",
                    )}
                  </p>
                  {strings(profile.terms_urls).map((url) => (
                    <SourceLink
                      key={url}
                      url={url}
                      children={
                        url.includes("creativecommons.org")
                          ? "CC BY 4.0 licence"
                          : "Provider terms"
                      }
                    />
                  ))}
                  {strings(profile.publication_restrictions).length > 0 && (
                    <ul>
                      {strings(profile.publication_restrictions).map(
                        (restriction) => (
                          <li key={restriction}>{restriction}</li>
                        ),
                      )}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
        <div className="row small">
          <span>Currency: {text(countryMetadata?.currency)}</span>
          <span>Region: {text(countryMetadata?.region)}</span>
          {countryMetadata?.monetary_union === "EA" && (
            <span>
              Euro-area member · adoption {text(countryMetadata.euro_adoption)}
            </span>
          )}
        </div>
        {!notesWithheld &&
          records(countryMetadata?.notes).map((note, index) => (
            <p className="small" key={index}>
              {text(note.text, text(note.fx_regime_note))}
            </p>
          ))}
        <p className="small muted">
          {notesWithheld
            ? "Country notes are withheld pending review."
            : "Country notes require review before publication."}{" "}
          Source definitions and data availability can differ across countries.
        </p>
      </section>

      {!bundle && (
        <p role="status">Loading source metadata for {countryName}…</p>
      )}
      <section aria-label="Indicator definitions" className="indicator-grid">
        {visible.map((indicator) => {
          const card = bundle?.cards.find(
            (c) => c.concept_id === indicator.concept_id,
          );
          const segments = card?.source_segments ?? [];
          const publication = record(card?.publication);
          const excludedSources = records(publication.excluded_sources);
          const visibleReason = (code: string) =>
            !(
              excludedSources.length > 0 &&
              code === "no_verified_mapping_or_observations"
            );
          const sourceNames =
            card?.sources.join(", ") ||
            (excludedSources.length > 0
              ? `${[...new Set(excludedSources.map((source) => text(source.source, text(source.dataset))))].join(", ")} — not included`
              : "No mapped source");
          const adjustments = [
            ...new Set(segments.map((s) => text(s.sa_flag))),
          ];
          const units = [
            ...new Set(
              segments.map(
                (s) =>
                  `${text(s.unit_label, text(s.unit))}${s.unit_mult ? ` ×10^${text(s.unit_mult)}` : ""}`,
              ),
            ),
          ];
          const defaultTransform =
            card?.default_transform ?? indicator.default_transform ?? "level";
          return (
            <article key={indicator.concept_id} className="card stack">
              <div className="row between">
                <span className="overline">
                  {indicator.category ?? "Indicator"}
                </span>
                {card ? (
                  <Status status={card.status} />
                ) : (
                  <span className="badge draft">Not loaded</span>
                )}
              </div>
              <h3>{indicator.title}</h3>
              <p className="small">
                {card?.definition ?? indicator.definition ?? indicator.title}
              </p>
              <dl className="definition-list">
                <dt>Concept</dt>
                <dd>
                  <code>{indicator.concept_id}</code>
                </dd>
                <dt>Units</dt>
                <dd>{units.join("; ") || "Not reported"}</dd>
                <dt>Frequency</dt>
                <dd>
                  {text(
                    card?.frequency ??
                      indicator.frequency ??
                      indicator.native_frequency,
                  )}
                </dd>
                <dt>Adjustment</dt>
                <dd>{adjustments.join("; ") || "Not reported"}</dd>
                <dt>Observed</dt>
                <dd>
                  {card?.first_date && card.last_date
                    ? `${card.first_date} – ${card.last_date}`
                    : "No reported observations"}
                </dd>
                <dt>Transform</dt>
                <dd>
                  {transforms[defaultTransform] ?? defaultTransform}
                  <br />
                  <span className="mono">
                    {formulas[defaultTransform] ?? "See model definition"}
                  </span>
                </dd>
                <dt>Sources</dt>
                <dd>{sourceNames}</dd>
              </dl>
              {Number(publication.excluded_observations) > 0 && (
                <p
                  className="small warning-box"
                  data-testid="source-exclusion-note"
                >
                  <strong>Source data excluded from this candidate.</strong>{" "}
                  {text(
                    publication.reason,
                    "The source policy prevents redistribution of these observations.",
                  )}{" "}
                  {number(Number(publication.excluded_observations), 0)}{" "}
                  observations excluded;{" "}
                  {number(Number(publication.retained_observations), 0)}{" "}
                  retained.
                </p>
              )}
              {card?.stale && (
                <p className="small warning-box">
                  Stale series: its latest observation exceeds the freshness
                  threshold.
                </p>
              )}
              {card?.policy_label && (
                <p className="small info-box">{card.policy_label}</p>
              )}
              {card && card.status !== "available" && (
                <p className="small muted">
                  {card.reason_codes
                    .filter(visibleReason)
                    .map((code) =>
                      code === "publication_source_excluded"
                        ? "Source observations withheld under the publication policy"
                        : code.replaceAll("_", " "),
                    )
                    .join(" · ")}
                </p>
              )}
              <details>
                <summary>Sources, definitions & limitations</summary>
                {records(card?.variant_options).length > 0 && (
                  <section
                    aria-label="Additional data variants"
                    className="stack"
                  >
                    <h3>Additional data variants</h3>
                    <ul className="source-list">
                      {records(card?.variant_options).map((variant) => (
                        <li key={text(variant.label)}>
                          <strong>{text(variant.label)}</strong>
                          <p className="small">
                            {text(variant.start)}–{text(variant.end)} ·{" "}
                            {text(variant.unit)}
                            {variant.base_year
                              ? ` (${text(variant.base_year)} = 100)`
                              : ""}
                            {variant.country === "EA" &&
                            indicator.concept_id === "policy_rate"
                              ? ". Shared euro-area rate; national samples respect euro adoption."
                              : ""}
                          </p>
                          <p className="small">{text(variant.attribution)}</p>
                          <SourceLink
                            url={text(variant.source_url)}
                            children="Official series"
                          />
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
                {segments.length ? (
                  <ul className="source-list">
                    {segments.map((segment, index) => (
                      <li key={index} className="stack small">
                        <SourceLink
                          url={segment.source_url}
                          children={`${text(segment.source)} · source record`}
                        />
                        <p>
                          {text(
                            segment.definition,
                            "No additional source definition reported.",
                          )}
                        </p>
                        <dl className="definition-list">
                          <dt>Source ID</dt>
                          <dd>
                            <code>{text(segment.source_series_id)}</code>
                          </dd>
                          <dt>Coverage</dt>
                          <dd>
                            {text(segment.first_date)} –{" "}
                            {text(segment.last_date)}
                          </dd>
                          <dt>Price basis</dt>
                          <dd>
                            {text(segment.price_basis)} · base{" "}
                            {text(segment.base_year)}
                          </dd>
                          <dt>Attribution</dt>
                          <dd>{text(segment.attribution)}</dd>
                          <dt>Reuse status</dt>
                          <dd>
                            {text(segment.terms_status).replaceAll("_", " ")}
                          </dd>
                          {strings(segment.terms_urls).length > 0 && (
                            <>
                              <dt>Licences & terms</dt>
                              <dd>
                                {strings(segment.terms_urls).map((url) => (
                                  <div key={url}>
                                    <SourceLink
                                      url={url}
                                      children={
                                        url.includes("creativecommons.org")
                                          ? "CC BY 4.0 licence"
                                          : "Provider terms"
                                      }
                                    />
                                  </div>
                                ))}
                              </dd>
                            </>
                          )}
                          {strings(segment.publication_restrictions).length >
                            0 && (
                            <>
                              <dt>Reuse conditions</dt>
                              <dd>
                                <ul>
                                  {strings(
                                    segment.publication_restrictions,
                                  ).map((restriction) => (
                                    <li key={restriction}>{restriction}</li>
                                  ))}
                                </ul>
                              </dd>
                            </>
                          )}
                        </dl>
                      </li>
                    ))}
                  </ul>
                ) : excludedSources.length > 0 ? (
                  <div className="small">
                    <p>Mapped source data are excluded from this candidate.</p>
                    <ul>
                      {excludedSources.map((source, index) => (
                        <li key={index}>
                          <strong>
                            {text(source.source)} · {text(source.dataset)}
                          </strong>
                          : {text(source.reason)}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <p>
                    No verified source mapping is available for this country.
                  </p>
                )}
                {card && (
                  <p className="small muted">
                    Flags:{" "}
                    {[...new Set([...card.flags, ...card.warnings])]
                      .filter(visibleReason)
                      .map((flag) => flag.replaceAll("_", " "))
                      .join(" · ") || "None reported"}
                  </p>
                )}
              </details>
            </article>
          );
        })}
      </section>
      {!filtered.length && <p>No indicator matches these filters.</p>}
      <nav className="row between" aria-label="Indicator pages">
        <button
          disabled={currentPage === 0}
          onClick={() => setPage(currentPage - 1)}
        >
          Previous indicators
        </button>
        <span className="small">
          Page {currentPage + 1} of {pageCount}
        </span>
        <button
          disabled={currentPage + 1 >= pageCount}
          onClick={() => setPage(currentPage + 1)}
        >
          Next indicators
        </button>
      </nav>

      <section className="stack" aria-labelledby="coverage-title">
        <div>
          <h2 id="coverage-title">Coverage at a glance</h2>
          <p className="small muted">
            Country × indicator. Status is written in every cell; scroll
            horizontally for the full catalogue.
          </p>
        </div>
        <div className="row" aria-label="Coverage legend">
          {["available", "available_note", "limited", "missing"].map(
            (status) => (
              <Status key={status} status={status} />
            ),
          )}
        </div>
        <div
          className="table-wrap matrix-wrap"
          role="region"
          tabIndex={0}
          aria-label="Scrollable country and indicator coverage matrix"
        >
          <table>
            <caption className="visually-hidden">
              Coverage for every country and indicator in snapshot{" "}
              {manifest.snapshot_id}
            </caption>
            <thead>
              <tr>
                <th scope="col">Country</th>
                {manifest.indicators.map((i) => (
                  <th scope="col" key={i.concept_id}>
                    <abbr title={i.title}>{i.concept_id}</abbr>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {manifest.countries.map((c) => (
                <tr key={c.iso3}>
                  <th scope="row">{c.name}</th>
                  {manifest.indicators.map((i) => {
                    const entry = coverage.get(`${c.iso3}:${i.concept_id}`);
                    return (
                      <td
                        key={i.concept_id}
                        title={
                          entry
                            ? `${text(entry.first_date)} to ${text(entry.last_date)}; ${strings(entry.reason_codes).join(", ")}`
                            : "Coverage metadata unavailable"
                        }
                      >
                        {entry ? (
                          <Status status={text(entry.status)} />
                        ) : (
                          <span>Not reported</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function scientific(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toExponential(2)
    : "Not reported";
}

export function Methods({ manifest }: { manifest: Manifest }) {
  const localOnly =
    manifest.publication?.local_only_comparison === true ||
    manifest.publication?.source_mode === "all";
  const validation = records(manifest.validation.models);
  const matched = validation.filter(
    (v) =>
      typeof v.reference_max_abs_difference === "number" &&
      typeof v.reference_tolerance === "number" &&
      v.reference_max_abs_difference <= v.reference_tolerance,
  );
  const largestDifference = validation.reduce<number | null>(
    (maximum, row) =>
      typeof row.reference_max_abs_difference === "number"
        ? Math.max(maximum ?? 0, row.reference_max_abs_difference)
        : maximum,
    null,
  );
  return (
    <div className="stack">
      <header className="page-heading">
        <div className="overline">Transparent by design</div>
        <h1>Methods & validation</h1>
        <p>
          Every result depends on data, transformations and assumptions. Review
          the model, its reference checks and the limits of its interpretation.
        </p>
      </header>
      <section className="card stack" aria-labelledby="about-macrolab">
        <h2 id="about-macrolab">About MacroLab</h2>
        <p>MacroLab is a non-commercial research and teaching tool.</p>
        <p>
          Some sources are excluded for licensing reasons;{" "}
          <a href="#source-terms">see the data policy</a>.
        </p>
        <p>
          {buildVersion} · Data snapshot {snapshotDate(manifest.as_of_date)}.
          This is a fixed snapshot bundled with the app; it does not refresh
          while you browse. Six templates include a common ECB shock across
          countries and Türkiye exchange-rate pass-through, with matched VAR/LP
          comparisons available where supported. Country narratives are
          withheld.
        </p>
        {manifest.publication?.included_global_factors?.includes(
          "commod_idx",
        ) && (
          <p>
            Commodity indices: Source: International Monetary Fund, Primary
            Commodity Prices (PCPS). ECB data supply deposit-facility and
            main-refinancing rates and the official seasonally adjusted
            euro-area HICP variant. Source-specific attribution and terms appear
            below and on each series card.
          </p>
        )}
        <p>
          MacroLab is an interactive macroeconomics laboratory by{" "}
          <SourceLink
            url="https://hakangulmez.github.io/"
            children="Hakan Zeki Gülmez"
          />
          . Explore official data, estimate familiar models and see how the
          findings change with assumptions. Calculations run in your browser,
          and every result records its data snapshot, actual sample and
          sensitivity variants.
        </p>
      </section>
      <section className="overview-grid" aria-label="Validation summary">
        <div className="card stack">
          <span className="overline">Reference checks</span>
          <h2>
            {matched.length} / {manifest.models.length} models
          </h2>
          <p className="small">
            Reference differences within the recorded model-specific tolerance.
          </p>
        </div>
        <div className="card stack">
          <span className="overline">Largest difference</span>
          <h2 className="mono">{scientific(largestDifference)}</h2>
          <p className="small">
            Maximum absolute difference across the reported numerical reference
            checks.
          </p>
        </div>
        <div className="card stack">
          <span className="overline">Validation record</span>
          <h2>{text(manifest.validation.gate)}</h2>
          <p className="small">
            Code version {text(manifest.validation.code_version)} ·
            deterministic fixtures and fixed-seed recovery tests.
          </p>
        </div>
      </section>
      <div className="warning-box">
        <strong>Interpretation comes first.</strong>
        <p>
          Regression describes association. Granger tests measure predictive
          content. Identified VAR responses are conditional model scenarios
          whose meaning depends on the ordering and shock definition; they are
          not forecasts or automatic causal estimates.
        </p>
      </div>
      <section className="stack" aria-labelledby="models-methods">
        <h2 id="models-methods">Released methods</h2>
        <div className="model-grid">
          {manifest.models.map((model) => {
            const evidence = validation.find((v) => v.model_id === model.id);
            const recovery = record(evidence?.recovery);
            return (
              <article className="card model-card" key={model.id}>
                <div className="row between">
                  <span className="badge">
                    {model.family.replaceAll("_", " ")}
                  </span>
                  <code>{model.id}</code>
                </div>
                <h3>{model.title}</h3>
                <p>{model.summary}</p>
                <span className="small muted">{model.label}</span>
                <dl className="definition-list">
                  <dt>Runtime</dt>
                  <dd>{model.runtime}</dd>
                  <dt>Reference Δ</dt>
                  <dd className="mono">
                    {scientific(evidence?.reference_max_abs_difference)}
                  </dd>
                  <dt>Tolerance</dt>
                  <dd className="mono">
                    {scientific(evidence?.reference_tolerance)}
                  </dd>
                </dl>
                <details>
                  <summary>Assumptions, tests & references</summary>
                  <ul>
                    {model.assumptions.map((assumption) => (
                      <li key={assumption}>{assumption}</li>
                    ))}
                  </ul>
                  <p className="small">
                    Inputs: {text(model.inputs.min_series)}–
                    {text(model.inputs.max_series)} selected series;{" "}
                    {strings(model.inputs.frequencies).join(" / ")} frequency.
                  </p>
                  {Object.keys(record(evidence?.reference_outputs)).length >
                    0 && (
                    <p className="small">
                      Reference outputs:{" "}
                      {Object.keys(record(evidence?.reference_outputs))
                        .map((key) => key.replaceAll("_", " "))
                        .join(", ")}
                      .
                    </p>
                  )}
                  {typeof recovery.coverage === "number" && (
                    <p className="small">
                      Fixed-seed coverage: {number(recovery.coverage * 100, 1)}%
                      against a{" "}
                      {typeof recovery.nominal_coverage === "number"
                        ? `${number(recovery.nominal_coverage * 100, 1)}%`
                        : "reported"}{" "}
                      nominal interval. Replications:{" "}
                      {text(recovery.replications ?? recovery.repetitions)}.
                      This simulation is not proof of calibration for every
                      empirical sample.
                    </p>
                  )}
                  {recovery.status === "not_applicable" && (
                    <p className="small">
                      Recovery coverage is not applicable to this descriptive or
                      deterministic method.
                    </p>
                  )}
                  {strings(evidence?.limitations).map((item) => (
                    <p className="small" key={item}>
                      {item}
                    </p>
                  ))}
                  <ul>
                    {model.references.map((reference) => (
                      <li key={reference.url}>
                        <SourceLink
                          url={reference.url}
                          children={reference.title}
                        />
                      </li>
                    ))}
                  </ul>
                </details>
              </article>
            );
          })}
        </div>
      </section>
      <section className="card stack" aria-labelledby="source-terms">
        <h2 id="source-terms">Data sources & reuse terms</h2>
        <p className="small muted">
          {localOnly
            ? "This local comparison retains the full snapshot, including sources not cleared for publication. It is not a publication candidate."
            : manifest.publication?.mode === "static_candidate"
              ? "The full local review snapshot covers more sources than this static candidate. The source policy below determines which observations are included here."
              : "These are local review data. A working public endpoint is not permission to redistribute every underlying series."}{" "}
          The exact provider, attribution and reuse status are retained on each
          indicator card.
        </p>
        {manifest.publication && (
          <div
            className="info-box small"
            data-testid="publication-source-policy"
          >
            <h3>
              {localOnly
                ? "Sources not cleared for publication"
                : "Excluded source records"}
            </h3>
            <p>
              {localOnly
                ? "All retrieved observations are retained for local comparison. The sources below are not cleared for publication."
                : `${number(manifest.publication.excluded_observations, 0)} observations were excluded from this candidate. Excluded observations are absent from its data files and calculations.`}
            </p>
            <ul>
              {manifest.publication.excluded_sources.map((source, index) => (
                <li key={index}>
                  <strong>
                    {text(source.source, text(source.id))} ·{" "}
                    {text(source.dataset)}
                  </strong>
                  : {text(source.reason, text(source.status))}
                </li>
              ))}
            </ul>
            {!localOnly && manifest.publication.excluded_concepts?.length ? (
              <ul data-testid="excluded-concepts">
                {manifest.publication.excluded_concepts.map((concept) => (
                  <li key={concept.concept_id}>
                    <strong>{concept.title}.</strong> {concept.reason}
                  </li>
                ))}
              </ul>
            ) : null}
            {manifest.publication.notes_withheld && (
              <p>Country notes are withheld pending review.</p>
            )}
          </div>
        )}
        <ul className="source-list">
          {manifest.sources.map((source, index) => (
            <li key={index}>
              <div className="row between">
                <h3>{text(source.name)}</h3>
                <SourceLink url={source.terms_url} children="Provider terms" />
              </div>
              <p className="small">{text(source.terms_status)}</p>
              <p className="small muted">{text(source.attribution)}</p>
              {strings(source.restrictions).length > 0 && (
                <ul className="small">
                  {strings(source.restrictions).map((restriction) => (
                    <li key={restriction}>{restriction}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section className="card stack" aria-labelledby="diagnostic-rules">
        <h2 id="diagnostic-rules">How checks are presented</h2>
        <p className="small">
          Counts show distinct findings: identical codes and messages are
          grouped across countries, responses and horizons. Technical details
          and exports retain every original instance. If severities differ, the
          most serious instance determines the group’s tier.
        </p>
        <p className="small">
          Observations per estimated parameter are a rule of thumb, not a test
          of validity. Fewer than 5 produces an amber warning; 5 to below 10
          produces a collapsed note; 10 or more produces no ratio message. The
          count uses the actual estimation sample and the fitted equation,
          including its intercept, lags and exogenous controls. Separate checks
          still block a model that cannot be estimated.
        </p>
        <p className="small">
          Stationarity findings for exogenous controls are notes because the
          model conditions on their selected paths. They remain in the technical
          details and exports; a note does not establish that a control is
          valid. Endogenous stationarity findings retain their usual severity.
        </p>
        <p className="small">
          Builder checks start with coverage. Running adds prepared-data
          diagnostics and checks on the fitted model. Results identify findings
          that depend on estimation, and technical details retain when each
          check was computed.
        </p>
      </section>
      <section className="card stack" aria-labelledby="v1-inference">
        <h2 id="v1-inference">V1 template inference</h2>
        <p>
          Lag-augmented HC1 is the new template default after a fixed synthetic
          coverage comparison; HAC remains a sensitivity option. This does not
          guarantee nominal coverage in real data.
        </p>
        <p>
          ECB conditional bands ignore first-stage shock estimation. The joint
          action re-estimates both stages on an explicit common window. Both are
          pointwise intervals. National VARs use different method and different
          identification and are excluded from same-estimand agreement counts.
        </p>
        <p>
          Cumulative responses are 100 × (log Y at the horizon − log Y before
          the impulse), without annualisation. Growth is an alternative display.
          NSA prices use calendar dummies; the app never seasonally adjusts
          source observations.
        </p>
      </section>
      <section className="card stack" aria-labelledby="response-methods">
        <h2 id="response-methods">LP, VAR and two-step shocks</h2>
        <p>
          A VAR estimates a dynamic system and iterates its coefficients to
          trace a response. Local projections (LP) fit a separate regression at
          each horizon. Different lag restrictions can produce different paths
          even with the same sample and shock. MacroLab never averages them.
        </p>
        <p>
          The matched method view refits a common anchor window and gives both
          methods the same dated recursive innovation and physical
          normalization. LP future outcomes extend beyond that window. Its
          horizon-by-horizon sign and interval-overlap counts apply only inside
          the pair; a raw-impulse baseline or a separately identified national
          VAR is a different estimand.
        </p>
        <ol>
          <li>
            Estimate the EA first-stage VAR and recover its orthogonalised DFR
            residuals.
          </li>
          <li>
            Use that same dated shock in each national LP, with each actual
            sample displayed.
          </li>
          <li>
            Show conditional HC1 bands or compute the on-demand joint bootstrap
            on its common window.
          </li>
        </ol>
        <p>
          The estimated shock is a generated regressor. Conditional bands treat
          it as known and understate total uncertainty; the joint bootstrap
          re-estimates both stages under its stated window and stability limits.
          Overlapping country peak intervals do not support a ranking. Peak
          selection is descriptive, not an equality test.
        </p>
        <h3>Pass-through ratios</h3>
        <p>
          The headline ratio is cumulative CPI response divided by cumulative
          depreciation from the same impulse. For NEER, depreciation is the
          negative of its cumulative response. The HC1 delta-method interval
          uses the joint CPI/NEER coefficient covariance. Near-zero or weak
          denominators make ratios unreliable; warnings and undefined points
          stay visible. The secondary CPI path is the response to an initial 1%
          depreciation, followed by the exchange rate’s own subsequent path.
        </p>
        <h3>Stability rule</h3>
        <p>
          First-stage shock extraction uses orthogonalised residuals and does
          not require stable dynamics. A largest companion root of 0.98 or above
          warns; 1 or above indicates instability. Unstable v1 VAR IRFs, FEVD,
          historical decompositions and simulation-based joint bands remain
          blocked. The accepted v0 extended-VAR sensitivity retains its
          historical warning and numerical baseline.
        </p>
        <p className="small muted">
          Historical-decomposition views, country narratives and further Türkiye
          crisis options are deferred to v1.1. Forecasting, BVAR, panels and
          cointegration are planned for v2; sign restrictions, proxy
          instruments, state dependence and TVP-VAR are planned for v3.
        </p>
      </section>
      <section className="card stack" aria-labelledby="limits">
        <h2 id="limits">Limits to keep in view</h2>
        <ul className="stack small">
          <li>
            The recorded snapshot freezes retrieved observations, not the
            provider’s historical real-time vintages. Later revisions can change
            estimates.
          </li>
          <li>
            V0 models use a contiguous common sample, without interpolation. V1
            LP exclusions preserve calendar gaps and drop affected lag/target
            rows. Transformations, missing data and model lags can shorten the
            requested window.
          </li>
          <li>
            Monthly-to-quarterly and annual conversions require explicit rules
            and complete periods. Different units, adjustments or source
            definitions are not silently combined.
          </li>
          <li>
            Euro-area policy rates are shared after adoption. Country responses
            can differ, but there is no separate national monetary-policy shock
            during that period.
          </li>
          <li>
            COVID treatment, sample dates, ordering and lag choices can
            materially change results. Sensitivity summaries compare the
            variants actually computed.
          </li>
          <li>
            Bootstrap intervals are pointwise, condition on the fitted lag and
            fixed exogenous paths, and do not remove model uncertainty.
            Non-stationarity and unstable dynamics require interpretation.
          </li>
          <li>
            {manifest.publication?.notes_withheld
              ? "Country notes are withheld pending review."
              : "Country notes are drafts."}{" "}
            Missing or limited coverage remains visible, and source-specific
            reuse restrictions still apply.
          </li>
        </ul>
      </section>
    </div>
  );
}
