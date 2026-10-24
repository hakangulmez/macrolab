import type { AnalysisConfig, Manifest } from "../types";
import { diagnosticModel } from "../diagnosticModels";
import { title } from "../format";
import { Field } from "./Common";
export function DiagnosticControls({
  config,
  manifest,
  update,
}: {
  config: AnalysisConfig;
  manifest: Manifest;
  update: (fn: (c: AnalysisConfig) => void) => void;
}) {
  if (!diagnosticModel(config.model.id)) return null;
  const p = config.model.params,
    isBreak = config.model.id === "test.break";
  const input = (
    key: string,
    label: string,
    fallback: number,
    min: number,
    max: number,
  ) => (
    <Field label={label}>
      <input
        type="number"
        min={min}
        max={max}
        value={Number(p[key] ?? fallback)}
        onChange={(e) =>
          update((c) => {
            c.model.params[key] = Number(e.target.value);
          })
        }
      />
    </Field>
  );
  const select = (
    key: string,
    label: string,
    fallback: string,
    choices: [string, string][],
  ) => (
    <Field label={label}>
      <select
        value={String(p[key] ?? fallback)}
        onChange={(e) =>
          update((c) => {
            c.model.params[key] = e.target.value;
          })
        }
      >
        {choices.map(([v, label]) => (
          <option key={v} value={v}>
            {label}
          </option>
        ))}
      </select>
    </Field>
  );
  return (
    <section className="stack" aria-label="Diagnostic assumptions">
      <h3>
        {isBreak ? "Host equation and break tests" : "Long-run specification"}
      </h3>
      {isBreak ? (
        <>
          {select("host", "Host equation", "sing.ols", [
            ["sing.ols", "Linear regression"],
            ["sing.ardl", "ARDL"],
            ["ident.external_series", "First-stage policy-rate equation"],
          ])}
          {p.host === "ident.external_series" && (
            <p className="small">
              Policy data variant: {String(p.source_variant ?? "none")}; the ECB
              attachment carries its selected policy measure and official SA
              HICP.
            </p>
          )}
          <p className="small">
            Attach from a regression or ECB result to carry its exact inputs and
            specification. Sup-F uses 15% trimming. Calendar dummies remain
            stable nuisance terms.
          </p>
          {select("inference", "Sup-F calibration", "hac_bootstrap", [
            ["hac_bootstrap", "Fixed-regressor bootstrap · HAC Wald"],
            [
              "hc_bootstrap",
              "HC fixed-regressor bootstrap · conventional Wald",
            ],
            ["hac_asymptotic", "HAC asymptotic"],
            ["conventional_asymptotic", "Conventional asymptotic"],
          ])}
          {select("covariance", "Host fixed-date Wald covariance", "HAC", [
            ["HAC", "Newey–West HAC"],
            ["HC1", "Heteroskedasticity robust HC1"],
            ["conventional", "Conventional"],
          ])}
          {p.covariance !== "conventional" &&
            input("hac_lags", "HAC lags", 4, 0, 24)}
          <Field label="Chow break date (first period of second regime)">
            <input
              value={String(p.break_date ?? "")}
              placeholder={config.frequency === "M" ? "2020-03" : "2020-Q1"}
              onChange={(e) =>
                update((c) => {
                  c.model.params.break_date = e.target.value;
                })
              }
            />
          </Field>
          {input("lags", "Host dependent lags", 1, 1, 24)}
          {input("order", "Host regressor lags (ARDL)", 1, 1, 24)}
          {select("trend", "Host deterministic term", "c", [
            ["c", "Constant"],
            ["n", "No constant"],
          ])}
        </>
      ) : (
        <>
          <p className="small">
            Only levels or log levels. Select Include for COVID: the pinned
            Johansen test has no external-regressor interface. Critical values
            are asymptotic, with possible small-sample size distortion.
          </p>
          {select(
            "deterministic",
            "Johansen and VECM deterministic case",
            "constant",
            [
              ["none", "No deterministic terms (case I)"],
              ["constant", "Unrestricted constant (case III)"],
              [
                "linear_trend",
                "Unrestricted constant and linear trend (case V)",
              ],
            ],
          )}
          {input(
            "lags",
            "VAR lags (VECM difference lags = VAR lags − 1)",
            2,
            1,
            12,
          )}
          {select("eg_trend", "Engle–Granger trend", "c", [
            ["n", "No deterministic term"],
            ["c", "Constant"],
            ["ct", "Constant and linear trend"],
            ["ctt", "Constant, linear and quadratic trend"],
          ])}
          {input("eg_lags", "Engle–Granger residual ADF lags", 4, 0, 24)}
          {config.model.id === "vecm" && (
            <>
              {input(
                "rank",
                "User-chosen cointegration rank",
                1,
                0,
                config.series.length,
              )}
              {input("horizon", "Response horizon", 20, 1, 48)}
              {input(
                "draws",
                "Rank-fixed bootstrap draws (0 disables bands)",
                200,
                0,
                1000,
              )}
              {select(
                "shock",
                "Recursive impulse",
                config.series[0]?.concept_id ?? "",
                config.series.map((s) => [
                  s.concept_id,
                  title(s.concept_id, manifest.indicators),
                ]),
              )}
              <p className="small">
                Recursive order is the indicator order above. VECM responses can
                be permanent; they need not return to zero.
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
