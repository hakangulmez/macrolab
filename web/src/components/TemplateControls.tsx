import type { AnalysisConfig } from "../types";
import { Field } from "./Common";
import { TemplateSources } from "./TemplateSources";
export function TemplateControls({
  config,
  update,
}: {
  config: AnalysisConfig;
  update: (fn: (c: AnalysisConfig) => void) => void;
}) {
  const p = config.model.params,
    ecb = p.template_id === "same_ecb_shock";
  if (!p.template_id) return null;
  if (
    [
      "ea_phillips_pooled",
      "same_ecb_shock_pooled",
      "ea_inflation_horse_race",
    ].includes(String(p.template_id))
  )
    return (
      <section className="card stack" aria-label="Template assumptions">
        <h3>Template assumptions</h3>
        <p>
          {p.template_id === "ea_phillips_pooled"
            ? "Year-on-year HICP inflation and Brent growth. The HP unemployment gap (λ = 1600) is two-sided and uses later observations. Country fixed effects; Driscoll–Kraay intervals and country OLS HAC(4)."
            : p.template_id === "same_ecb_shock_pooled"
              ? "HICP and GDP responses to the existing EA DFR shock. Common country and horizon windows, lag-augmented LP, Driscoll–Kraay conditional bands. Time effects would absorb the common shock."
              : "Predict year-on-year EA HICP inflation itself. The first origin has 40 usable quarters; orders are fixed there. No exogenous regressors; BVAR λ = 0.2, two lags. Final-vintage data."}
        </p>
        <p className="small">
          The preregistered specification sensitivity rows run with the baseline
          and retain their exact samples and warnings.
        </p>
      </section>
    );
  const first = p.first_stage as AnalysisConfig | undefined;
  return (
    <section className="card stack" aria-label="Template assumptions">
      <h3>{ecb ? "Same ECB shock" : "Türkiye pass-through"}</h3>
      <p className="small">
        {ecb
          ? "DFR is the consistent policy series. National NSA HICP uses quarterly seasonal controls; EA HICP is officially seasonally adjusted. No shadow rate is available for 2014–2022."
          : "A 1% depreciation, with monthly seasonal controls. Conditional association; optional currency-crisis analysis has a separate sensitivity summary."}
      </p>
      {ecb && <TemplateSources config={config} />}
      {ecb && (
        <>
          <Field label="Policy measure">
            <select
              value={String(p.policy_measure)}
              onChange={(e) =>
                update((c) => {
                  c.model.params.policy_measure = e.target.value;
                })
              }
            >
              <option value="dfr">ECB deposit facility rate (DFR)</option>
              <option value="rate_3m">EA 3-month rate</option>
              <option value="bis">BIS policy rate</option>
            </select>
          </Field>
          <p className="small">
            The BIS series switches from MRO to DFR on 18 September 2024.
          </p>
          <Field label="Country window">
            <select
              value={String(p.country_window)}
              onChange={(e) =>
                update((c) => {
                  c.model.params.country_window = e.target.value;
                })
              }
            >
              <option value="own">Each country’s available window</option>
              <option value="common">Common window across countries</option>
            </select>
          </Field>
          <Field label="Uncertainty band">
            <select
              data-testid="uncertainty-band"
              aria-label="Uncertainty band"
              value={String(p.displayed_band)}
              onChange={(e) =>
                update((c) => {
                  c.model.params.displayed_band = e.target.value;
                  if (e.target.value === "joint")
                    c.model.params.country_window = "common";
                })
              }
            >
              <option value="conditional">
                Conditional · ignores first-stage uncertainty
              </option>
              <option value="joint">
                Joint bootstrap · both stages · 200 draws
              </option>
            </select>
          </Field>
          <Field label="ECB shock size">
            <select
              value={
                first?.outputs.irf?.shock_mode === "one_sd" ? "one_sd" : "0.25"
              }
              onChange={(e) =>
                update((c) => {
                  const f = c.model.params.first_stage as AnalysisConfig;
                  f.outputs.irf = {
                    ...f.outputs.irf!,
                    shock_mode:
                      e.target.value === "one_sd" ? "one_sd" : "fixed",
                    shock_size: e.target.value === "one_sd" ? 1 : 0.25,
                  };
                })
              }
            >
              <option value="one_sd">One identified standard deviation</option>
              <option value="0.25">+25 bp</option>
            </select>
          </Field>
        </>
      )}
      <Field label="LP inference">
        <select
          value={p.lag_augmented ? "augmented" : "HAC"}
          onChange={(e) =>
            update((c) => {
              c.model.params.lag_augmented = e.target.value === "augmented";
              c.model.params.covariance =
                e.target.value === "augmented" ? "HC1" : "HAC";
            })
          }
        >
          <option value="augmented">Lag-augmented LP · HC1</option>
          <option value="HAC">LP · HAC</option>
        </select>
      </Field>
      <Field label="Price / output response display">
        <select
          value={
            ecb
              ? String((p.response_modes as Record<string, string>).cpi)
              : String(p.response_mode)
          }
          onChange={(e) =>
            update((c) => {
              if (ecb)
                c.model.params.response_modes = {
                  gdp_real: e.target.value,
                  cpi: e.target.value,
                  unemp: "change",
                };
              else c.model.params.response_mode = e.target.value;
              c.model.params.growth_scale = ecb ? 4 : 1;
            })
          }
        >
          <option value="cumulative_log">
            Cumulative % change in the level
          </option>
          <option value="growth_log">
            Growth-rate response {ecb ? "(annualised)" : "(monthly)"}
          </option>
        </select>
      </Field>
    </section>
  );
}
