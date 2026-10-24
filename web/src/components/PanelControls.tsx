import type { AnalysisConfig, Manifest } from "../types";
import { Field } from "./Common";

export function PanelControls({
  config,
  manifest,
  update,
}: {
  config: AnalysisConfig;
  manifest: Manifest;
  update: (fn: (c: AnalysisConfig) => void) => void;
}) {
  if (!config.model.id.startsWith("panel.")) return null;
  const lp = config.model.id === "panel.lp",
    p = config.model.params;
  const common = (p.shock_type ?? "common") === "common";
  return (
    <div className="stack" data-testid="panel-controls">
      {lp && (
        <>
          <Field label="Panel shock source">
            <select
              value={
                p.first_stage ? "ea" : common ? "common" : "country_specific"
              }
              onChange={(e) =>
                update((c) => {
                  c.model.params.shock_type =
                    e.target.value === "country_specific"
                      ? "country_specific"
                      : "common";
                  if (e.target.value !== "country_specific")
                    c.model.params.effects = "country";
                  if (e.target.value === "ea") {
                    const original = manifest.templates.find(
                      (t) => t.id === "same_ecb_shock",
                    )!.config;
                    c.model.params.first_stage_source = "ecb_dfr";
                    c.model.params.first_stage = structuredClone(
                      original.model.params.first_stage,
                    );
                    c.series = c.series.filter(
                      (s) =>
                        s.role !== "shock" &&
                        s.concept_id !== "identified_impulse",
                    );
                    c.series.push({
                      concept_id: "identified_impulse",
                      role: "shock",
                      transform: "level",
                      transform_params: {},
                    });
                  } else {
                    delete c.model.params.first_stage;
                    c.model.params.first_stage_source = "selected";
                    c.series = c.series.filter(
                      (s) => s.concept_id !== "identified_impulse",
                    );
                  }
                })
              }
            >
              <option value="common">
                Selected series · common across countries
              </option>
              <option value="country_specific">
                Selected series · country-specific
              </option>
              <option value="ea">
                Identified euro-area shock · existing DFR first stage
              </option>
            </select>
          </Field>
          {Boolean(p.first_stage) && (
            <p className="small muted">
              Uses the existing recursive EA shock. Restrict the national sample
              to its observed first-stage window. Bands condition on the
              estimated shock and ignore first-stage uncertainty.
            </p>
          )}
        </>
      )}
      <Field label="Fixed effects">
        <select
          aria-describedby={lp && common ? "panel-time-reason" : undefined}
          value={String(p.effects ?? "country")}
          onChange={(e) =>
            update((c) => {
              c.model.params.effects = e.target.value;
            })
          }
        >
          <option value="country">Country effects</option>
          <option value="two_way" disabled={lp && common}>
            Country and time effects
          </option>
        </select>
      </Field>
      {lp && common && (
        <p id="panel-time-reason" className="small muted">
          Time effects are disabled with a common shock because they absorb the
          shock.
        </p>
      )}
      <Field label="Panel covariance">
        <select
          value={String(p.covariance ?? "Driscoll-Kraay")}
          onChange={(e) =>
            update((c) => {
              c.model.params.covariance = e.target.value;
            })
          }
        >
          {["Driscoll-Kraay", "country-clustered", "conventional"].map((v) => (
            <option key={v}>{v}</option>
          ))}
          {lp &&
            config.countries.length === 1 &&
            ["HC1", "HAC"].map((v) => <option key={v}>{v}</option>)}
        </select>
      </Field>
      {lp && (
        <>
          <Field label="Response definition">
            <select
              value={String(p.response_mode ?? "change")}
              onChange={(e) =>
                update((c) => {
                  c.model.params.response_mode = e.target.value;
                })
              }
            >
              <option value="change">Change from pre-impulse level</option>
              <option value="cumulative_log">
                Cumulative % change in level (log input)
              </option>
              <option value="level">Level</option>
              <option value="growth_log">Growth response (log input)</option>
            </select>
          </Field>
          <label className="row">
            <input
              type="checkbox"
              checked={p.lag_augmented !== false}
              onChange={(e) =>
                update((c) => {
                  c.model.params.lag_augmented = e.target.checked;
                })
              }
            />
            Lag augmentation (one extra lag)
          </label>
          <Field label="Country sample window">
            <select
              value={String(p.country_window ?? "own")}
              onChange={(e) =>
                update((c) => {
                  c.model.params.country_window = e.target.value;
                })
              }
            >
              <option value="own">Each country's observed sample</option>
              <option value="common">
                Common estimation dates across countries
              </option>
            </select>
          </Field>
        </>
      )}
      <p className="small muted">
        Pooled estimates and country columns use matching estimation dates.
        Missing inputs block; gaps are never filled. Covariance sensitivities
        remain visible.
      </p>
    </div>
  );
}
