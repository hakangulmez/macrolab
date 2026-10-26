import { countryIndicators } from "../displayLabels";
import { useState } from "react";
import type { AnalysisConfig, Manifest } from "../types";
import { Field } from "./Common";
import { title, transforms } from "../format";
import { analysisErrorMessage } from "../analysisErrors";
import { builderGuidance, firstStageDraft } from "../builderGuidance";

/** Draft controls are applied only by an explicit click; existing fields survive unchanged. */
export function FirstStageInput({
  config,
  manifest,
  update,
}: {
  config: AnalysisConfig;
  manifest: Manifest;
  update: (fn: (next: AnalysisConfig) => void) => void;
}) {
  const [draft, setDraft] = useState(() => firstStageDraft(config));
  const [json, setJson] = useState(JSON.stringify(draft, null, 2));
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(
    Boolean(config.model.params.first_stage),
  );
  const edit = (fn: (c: AnalysisConfig) => void) => {
    const c = structuredClone(draft);
    fn(c);
    setDraft(c);
    setJson(JSON.stringify(c, null, 2));
    setApplied(false);
    setError("");
  };
  const order = draft.identification?.params.order ?? [];
  const indicators = countryIndicators(manifest.indicators, draft.countries[0]);
  const reorder = (c: AnalysisConfig) => {
    const ids = c.series
      .filter((s) => ["endogenous", "response", "shock"].includes(s.role))
      .map((s) => s.concept_id);
    c.identification = {
      id: "recursive",
      params: {
        order: [
          ...(c.identification?.params.order ?? []).filter((id) =>
            ids.includes(id),
          ),
          ...ids.filter((id) => !c.identification?.params.order.includes(id)),
        ],
      },
    };
  };
  const apply = (c: AnalysisConfig) => {
    try {
      if (
        !c ||
        !Array.isArray(c.series) ||
        !Array.isArray(c.countries) ||
        !c.model ||
        !c.sample ||
        !c.special_periods
      )
        throw new Error("Enter a complete first-stage configuration.");
      if (
        c.countries.length !== 1 ||
        c.frequency !== config.frequency ||
        c.snapshot_id !== config.snapshot_id
      )
        throw new Error(
          "First stage needs one country and the same frequency and snapshot as stage two.",
        );
      const model = manifest.models.find((m) => m.id === "ident.recursive")!;
      const issues = builderGuidance(
        {
          ...c,
          model: {
            ...c.model,
            id: "ident.recursive",
            params: { ...c.model.params, template_id: undefined },
          },
        },
        model,
      );
      if (issues.length) throw new Error(issues.join(" "));
      update((next) => {
        next.model.params.first_stage = structuredClone(c);
      });
      setDraft(c);
      setJson(JSON.stringify(c, null, 2));
      setApplied(true);
      setError("");
    } catch (e) {
      setError(analysisErrorMessage(e));
    }
  };
  return (
    <section
      className="card stack first-stage-editor"
      aria-label="First-stage controls"
    >
      <h2>First-stage recursive VAR</h2>
      <p className="small muted">
        Choose one first-stage country, its series and ordering. These controls
        build the same configuration as Advanced JSON; nothing is applied until
        you choose Apply. Frequency and snapshot must match stage two.
      </p>
      <Field label="First-stage country">
        <select
          id="first-stage-config"
          aria-label="First-stage country"
          value={draft.countries[0] ?? ""}
          onChange={(e) =>
            edit((c) => {
              c.countries = [e.target.value];
            })
          }
        >
          {manifest.countries.map((c) => (
            <option key={c.iso3} value={c.iso3}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>
      <div className="two-fields">
        <Field label="First-stage lags">
          <input
            type="number"
            min={1}
            max={12}
            value={Number(draft.model.params.lags ?? 4)}
            onChange={(e) =>
              edit((c) => {
                c.model.params.lags = Number(e.target.value);
              })
            }
          />
        </Field>
        <Field label="First-stage COVID treatment">
          <select
            value={draft.special_periods.covid}
            onChange={(e) =>
              edit((c) => {
                c.special_periods.covid = e.target.value;
              })
            }
          >
            <option value="include">Include</option>
            <option value="dummy">Impulse dummies</option>
            <option value="exclude">Exclude</option>
          </select>
        </Field>
      </div>
      <div className="two-fields">
        <Field label="First-stage sample start">
          <input
            value={draft.sample.start}
            onChange={(e) =>
              edit((c) => {
                c.sample.start = e.target.value;
              })
            }
          />
        </Field>
        <Field label="First-stage sample end">
          <input
            value={draft.sample.end}
            onChange={(e) =>
              edit((c) => {
                c.sample.end = e.target.value;
              })
            }
          />
        </Field>
      </div>
      {draft.series.map((s, i) => (
        <div className="first-stage-series" key={s.concept_id}>
          <strong>{title(s.concept_id, indicators)}</strong>
          <Field label="Role">
            <select
              aria-label={`First-stage role for ${title(s.concept_id, indicators)}`}
              value={s.role}
              onChange={(e) =>
                edit((c) => {
                  c.series[i].role = e.target.value;
                  reorder(c);
                })
              }
            >
              <option value="endogenous">Endogenous</option>
              <option value="response">Response</option>
              <option value="shock">Shock</option>
              <option value="exogenous">Exogenous control</option>
              {!["endogenous", "response", "shock", "exogenous"].includes(
                s.role,
              ) && <option value={s.role}>{s.role} (choose a VAR role)</option>}
            </select>
          </Field>
          <Field label="Transform">
            <select
              aria-label={`First-stage transform for ${title(s.concept_id, indicators)}`}
              value={s.transform}
              onChange={(e) =>
                edit((c) => {
                  c.series[i].transform = e.target.value;
                  c.series[i].transform_params = {};
                })
              }
            >
              {Object.entries(transforms).map(([id, name]) => (
                <option value={id} key={id}>
                  {name}
                </option>
              ))}
            </select>
          </Field>
          <button
            aria-label={`Remove first-stage ${title(s.concept_id, indicators)}`}
            className="first-stage-remove"
            onClick={() =>
              edit((c) => {
                c.series.splice(i, 1);
                delete c.aggregation[s.concept_id];
                reorder(c);
              })
            }
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
      ))}
      <Field label="Add first-stage series">
        <select
          value=""
          onChange={(e) => {
            const id = e.target.value;
            if (id)
              edit((c) => {
                c.series.push({
                  concept_id: id,
                  role: "endogenous",
                  transform: "level",
                  transform_params: {},
                });
                c.aggregation[id] = "mean";
                reorder(c);
              });
          }}
        >
          <option value="">Choose an indicator…</option>
          {indicators
            .filter(
              (i) =>
                !draft.series.some((s) => s.concept_id === i.concept_id) &&
                (i.publication as { included?: boolean })?.included !== false,
            )
            .map((i) => (
              <option value={i.concept_id} key={i.concept_id}>
                {i.title}
              </option>
            ))}
        </select>
      </Field>
      <p className="small">
        Recursive order (earliest first). The Shock role selects the impulse.
      </p>
      <ol className="first-stage-order">
        {order.map((id, i) => (
          <li key={id}>
            <span>
              {i + 1}. {title(id, indicators)}
            </span>
            <button
              disabled={i === 0}
              aria-label={`Move first-stage ${title(id, indicators)} earlier`}
              onClick={() =>
                edit((c) => {
                  const a = c.identification!.params.order;
                  [a[i - 1], a[i]] = [a[i], a[i - 1]];
                })
              }
            >
              ↑
            </button>
            <button
              disabled={i === order.length - 1}
              aria-label={`Move first-stage ${title(id, indicators)} later`}
              onClick={() =>
                edit((c) => {
                  const a = c.identification!.params.order;
                  [a[i], a[i + 1]] = [a[i + 1], a[i]];
                })
              }
            >
              ↓
            </button>
          </li>
        ))}
      </ol>
      <button onClick={() => apply(draft)}>
        Apply first-stage configuration
      </button>
      <p role="status" className="small">
        {applied
          ? "First-stage configuration applied."
          : "Draft only; apply explicitly before running."}
      </p>
      {!config.series.some(
        (s) => s.concept_id === "identified_impulse" && s.role === "shock",
      ) && (
        <>
          <p className="small">
            Stage two must use the generated impulse. This action replaces the
            selected raw shock (or adds an impulse if none is selected); it does
            not alter the first-stage series.
          </p>
          <button
            disabled={!applied}
            onClick={() =>
              update((c) => {
                const i = c.series.findIndex((s) => s.role === "shock");
                const generated = {
                  concept_id: "identified_impulse",
                  role: "shock",
                  transform: "level",
                  transform_params: {},
                };
                if (i >= 0) {
                  delete c.aggregation[c.series[i].concept_id];
                  c.series[i] = generated;
                } else c.series.push(generated);
                c.aggregation.identified_impulse = "mean";
              })
            }
          >
            Use first-stage shock in stage two
          </button>
        </>
      )}
      <details>
        <summary>Advanced: first-stage JSON</summary>
        <Field label="First-stage configuration (JSON)">
          <textarea
            aria-label="First-stage configuration (JSON)"
            rows={8}
            value={json}
            onChange={(e) => setJson(e.target.value)}
          />
        </Field>
        <button
          onClick={() => {
            try {
              apply(JSON.parse(json) as AnalysisConfig);
            } catch (e) {
              setError(analysisErrorMessage(e));
            }
          }}
        >
          Apply JSON configuration
        </button>
      </details>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
