import { useState, type ReactNode } from "react";
import type { AnalysisConfig, Check, CountryBundle, Manifest } from "../types";
import {
  freshSimple,
  simpleQuestion,
  simpleSummary,
  seriesQuantity,
  entryUnits,
  sourceNotes,
  type Question,
} from "../simpleAnalysis";
import { countryIndicators } from "../displayLabels";
import { Checks, Field } from "./Common";
import { QuestionPicker } from "./QuestionPicker";
export function SimpleBuilder({
  manifest,
  config,
  setConfig,
  start,
  checks,
  bundles,
  busy,
  run,
  advanced,
  browse,
  check,
  recentResults,
  openSource,
}: {
  manifest: Manifest;
  config: AnalysisConfig;
  setConfig: (c: AnalysisConfig) => void;
  start: (q: Question) => void;
  checks: Check[];
  bundles: Record<string, CountryBundle>;
  busy: boolean;
  run: () => void;
  advanced: () => void;
  browse: () => void;
  check: () => void;
  recentResults: ReactNode;
  openSource: (country: string, concept: string) => void;
}) {
  const question = simpleQuestion(manifest, config);
  const [all, setAll] = useState(false);
  const [newQuestion, setNewQuestion] = useState(false);
  const isECB = config.model.id === "cmp.common_shock";
  const multi = question === "compare" || (question === "shock" && isECB);
  const blocked = checks.some((c) => c.level === "block");
  function replace(
    countries = config.countries,
    concepts = config.series.map((s) => s.concept_id),
  ) {
    if (!question) return;
    setConfig(
      freshSimple(manifest, question, {
        countries,
        concepts,
        preset: isECB ? "same_ecb_shock" : "monetary_policy",
      }),
    );
  }
  const indicators = countryIndicators(
    manifest.indicators,
    config.countries[0],
  );
  const recommended = ["unemp", "cpi", "gdp_real", "policy_rate", "oil_brent"];
  return (
    <section data-testid="screen-builder" className="simple-builder stack">
      <div className="page-heading">
        <span className="overline">Your workspace</span>
        <h1>Build an analysis</h1>
        <p>Start with a question. Inspect every assumption in Advanced.</p>
      </div>
      {!question ? (
        <div className="card stack">
          <p role="status">
            This analysis uses settings only available in Advanced
          </p>
          <p>
            Every setting is preserved. Return to Advanced to continue, or
            explicitly start a new question to replace this configuration.
          </p>
          <button onClick={advanced}>Continue in Advanced</button>
          <button onClick={() => setNewQuestion(true)}>
            Start a new Simple question
          </button>
          {newQuestion && (
            <QuestionPicker
              select={(q) => {
                start(q);
                setNewQuestion(false);
              }}
            />
          )}
        </div>
      ) : (
        <div className="card stack">
          <h2>1 · What do you want to do?</h2>
          <QuestionPicker value={question} select={start} />
          {question === "shock" && (
            <Field label="Shock preset">
              <select
                value={isECB ? "same_ecb_shock" : "monetary_policy"}
                onChange={(e) =>
                  setConfig(
                    freshSimple(manifest, "shock", {
                      preset: e.target.value as
                        "same_ecb_shock" | "monetary_policy",
                    }),
                  )
                }
              >
                <option value="monetary_policy">
                  US policy shock · recursive VAR
                </option>
                <option value="same_ecb_shock">
                  Same ECB shock · country local projections
                </option>
              </select>
            </Field>
          )}
          <h2>2 · {multi ? "Economies" : "Economy"}</h2>
          {multi && (
            <div className="country-chips">
              {config.countries.map((iso) => (
                <button
                  key={iso}
                  aria-label={`Remove ${manifest.countries.find((c) => c.iso3 === iso)?.name}`}
                  disabled={config.countries.length === 1}
                  onClick={() =>
                    replace(config.countries.filter((c) => c !== iso))
                  }
                >
                  {manifest.countries.find((c) => c.iso3 === iso)?.name} ×
                </button>
              ))}
            </div>
          )}
          <Field label={multi ? "Add economy" : "Economy"}>
            <select
              data-testid="simple-country"
              value={multi ? "" : config.countries[0]}
              disabled={question === "shock" && !isECB}
              onChange={(e) => {
                if (e.target.value)
                  replace(
                    multi
                      ? [...config.countries, e.target.value]
                      : [e.target.value],
                  );
              }}
            >
              {multi && <option value="">Choose an economy…</option>}
              {manifest.countries
                .filter(
                  (c) =>
                    (!multi || !config.countries.includes(c.iso3)) &&
                    (question !== "shock" ||
                      !isECB ||
                      (c.monetary_union === "EA" && c.iso3 !== "EA")),
                )
                .map((c) => (
                  <option key={c.iso3} value={c.iso3}>
                    {c.name}
                  </option>
                ))}
            </select>
          </Field>
          <h2>3 · Variables</h2>
          {question === "shock" ? (
            <p>
              The preset keeps its existing variables, ordering, transforms and
              controls. Inspect or customise them in Advanced.
            </p>
          ) : (
            <>
              {(question === "relate" ? [0, 1] : [0]).map((index) => (
                <Field
                  key={index}
                  label={
                    question === "relate"
                      ? index === 0
                        ? "Outcome"
                        : "Explanatory variable"
                      : "Indicator"
                  }
                >
                  <select
                    data-testid={`simple-variable-${index}`}
                    value={config.series[index]?.concept_id ?? ""}
                    onChange={(e) => {
                      const ids = config.series.map((s) => s.concept_id);
                      ids[index] = e.target.value;
                      replace(config.countries, ids);
                    }}
                  >
                    {!config.series[index] && (
                      <option value="">Choose the second variable…</option>
                    )}
                    {indicators
                      .filter(
                        (i) =>
                          all ||
                          recommended.includes(i.concept_id) ||
                          config.series.some(
                            (s) => s.concept_id === i.concept_id,
                          ),
                      )
                      .map((i) => (
                        <option
                          key={i.concept_id}
                          value={i.concept_id}
                          disabled={config.series.some(
                            (s, j) =>
                              j !== index && s.concept_id === i.concept_id,
                          )}
                        >
                          {i.title}
                        </option>
                      ))}
                  </select>
                </Field>
              ))}
              <button className="link" onClick={() => setAll(!all)}>
                {all
                  ? "Show suggested indicators"
                  : `Show all ${manifest.indicators.length} indicators`}
              </button>
            </>
          )}
          <section className="info-box stack" aria-label="What will run">
            <h2>4 · What will run</h2>
            <p data-testid="simple-summary">
              {simpleSummary(manifest, config, question)}
            </p>
            <p className="small">
              Frequency: {config.frequency}. Requested sample:{" "}
              {config.sample.start}–{config.sample.end}. Aggregation:{" "}
              {Array.from(new Set(Object.values(config.aggregation))).join(
                ", ",
              )}
              . Actual sample and dropped periods are reported in Results →
              Details → Samples &amp; data.
            </p>
            <ul>
              {config.series
                .filter((s) => s.concept_id !== "identified_impulse")
                .map((s) => (
                  <li key={s.concept_id}>
                    {seriesQuantity(manifest, config, s)} · {s.role} · units:{" "}
                    {entryUnits(bundles, config, s)}
                  </li>
                ))}
            </ul>
            {question === "forecast" && (
              <p className="small">
                Level input stays in source units: a price index produces a
                price-index forecast, not inflation. Eight periods means{" "}
                {config.frequency === "Q" ? "eight quarters" : "eight months"}.
              </p>
            )}
            {question === "compare" && (
              <p className="small">
                Descending ranks compare the transformed quantity, not welfare.
                Source definitions, units and adjustments may differ; no
                currency conversion or normalisation is added. Global factors
                repeat the same shared series and do not measure national
                variation.
              </p>
            )}
            <button className="link" onClick={advanced}>
              Inspect every setting in Advanced →
            </button>
            <button className="link" onClick={browse}>
              See all {manifest.models.length} methods →
            </button>
          </section>
          <details>
            <summary>
              Selected series: coverage, definitions and source notes
            </summary>
            {sourceNotes(manifest, config, bundles)
              .filter((x) => x.series.concept_id !== "identified_impulse")
              .map(({ iso, series, card, global }) => (
                <div key={iso + series.concept_id} className="section">
                  <strong>
                    {manifest.countries.find((c) => c.iso3 === iso)?.name} ·{" "}
                    {seriesQuantity(manifest, config, series)}
                  </strong>
                  <p>
                    {card?.status ?? "Loading coverage…"} ·{" "}
                    {card?.first_date ?? "—"}–{card?.last_date ?? "—"}
                    {global ? " · Shared global series" : ""}
                  </p>
                  <p>{card?.definition}</p>
                  {card?.warnings.map((w, i) => (
                    <p key={i}>{w}</p>
                  ))}
                  <button
                    className="link"
                    onClick={() => openSource(iso, series.concept_id)}
                  >
                    Open source card
                  </button>
                </div>
              ))}
          </details>
          <Checks
            checks={checks}
            countries={manifest.countries}
            indicators={manifest.indicators}
            onSourceCard={openSource}
          />
          <button onClick={check} disabled={busy}>
            Check compatibility
          </button>
          <button
            className="primary"
            data-testid="run-analysis"
            onClick={run}
            disabled={busy || blocked}
          >
            Run analysis →
          </button>
          <p className="small muted">
            {blocked
              ? "Resolve the required choices or blocking checks before running."
              : "The engine checks the selected data and sample before estimation. No missing series or economy is replaced."}
          </p>
        </div>
      )}
      {recentResults}
    </section>
  );
}
