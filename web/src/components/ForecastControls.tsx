import { forecastModel } from "../forecast";
import type { AnalysisConfig, Manifest } from "../types";
import { countryIndicators } from "../displayLabels";
import { text, title } from "../format";
import { Field } from "./Common";

export function ForecastControls({
  config,
  manifest,
  update,
}: {
  config: AnalysisConfig;
  manifest: Manifest;
  update: (fn: (c: AnalysisConfig) => void) => void;
}) {
  if (!forecastModel(config.model.id)) return null;
  const p = config.model.params,
    evalMode = config.model.id === "fc.eval",
    arima = config.model.id !== "fc.var";
  const indicators = countryIndicators(
    manifest.indicators,
    config.countries[0],
  );
  const targets = config.series.filter((s) => s.role !== "exogenous");
  const number = (
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
  return (
    <section className="stack" aria-label="Forecast assumptions">
      <h3>Forecast assumptions</h3>
      <p className="small muted">
        Final-vintage data; real-time performance may be worse. Future COVID
        dummies are zero. Forecasts return to the original indicator units.
      </p>
      {evalMode && (
        <>
          <Field label="Evaluation target">
            <select
              value={targets[0]?.concept_id ?? ""}
              onChange={(e) =>
                update((c) => {
                  const chosen = c.series.find(
                    (s) => s.concept_id === e.target.value,
                  )!;
                  c.series = [chosen, ...c.series.filter((s) => s !== chosen)];
                })
              }
            >
              {targets.map((s) => (
                <option value={s.concept_id} key={s.concept_id}>
                  {title(s.concept_id, indicators)}
                </option>
              ))}
            </select>
          </Field>
          <p className="small">
            RW, AR(BIC), ARIMA and BVAR are always included. First origin:{" "}
            {config.frequency === "M"
              ? "120 months; horizons 1, 6, 12 months"
              : "40 quarters; horizons 1, 4, 8 quarters"}
            . All transforms and BVAR scales use each origin’s training prefix.
          </p>
          <label className="check-row">
            <input
              type="checkbox"
              checked={Boolean(p.reselect)}
              onChange={(e) =>
                update((c) => {
                  c.model.params.reselect = e.target.checked;
                })
              }
            />
            Re-select ARIMA and benchmark AR orders at every origin (slower)
          </label>
        </>
      )}
      {!evalMode &&
        number(
          "horizon",
          "Forecast horizon",
          8,
          1,
          config.frequency === "M" ? 24 : 12,
        )}
      {config.model.id === "fc.var" && (
        <Field label="Forecast estimator">
          <select
            value={text(p.estimator, "ols")}
            onChange={(e) =>
              update((c) => {
                c.model.params.estimator = e.target.value;
              })
            }
          >
            <option value="ols">OLS VAR · re-estimated bootstrap</option>
            <option value="bvar">BVAR · posterior predictive</option>
          </select>
        </Field>
      )}
      {config.model.id !== "uni.arima" && (
        <>
          {number("lags", "VAR lags", 2, 1, 12)}
          {number("draws", "Predictive draws", 500, 100, 5000)}
          {(evalMode || p.estimator === "bvar") && (
            <Field label="Minnesota tightness λ">
              <input
                type="number"
                min={0.001}
                step={0.05}
                value={Number(p.lambda ?? 0.2)}
                onChange={(e) =>
                  update((c) => {
                    c.model.params.lambda = Number(e.target.value);
                  })
                }
              />
            </Field>
          )}
        </>
      )}
      <Field label="Future exogenous path">
        <select
          value={text(p.future_exog, "unspecified")}
          onChange={(e) =>
            update((c) => {
              c.model.params.future_exog = e.target.value;
            })
          }
        >
          <option value="unspecified">
            Not specified (blocks if exogenous series selected)
          </option>
          <option value="hold_last">Held at last transformed value</option>
          <option value="zero">Zero in transformed units</option>
        </select>
      </Field>
      {arima && (
        <>
          <Field label="ARIMA order selection">
            <select
              value={text(p.order_selection, "aicc")}
              onChange={(e) =>
                update((c) => {
                  c.model.params.order_selection = e.target.value;
                })
              }
            >
              <option value="aicc">AICc search · p, q ≤ 4</option>
              <option value="fixed">Fix the order</option>
            </select>
          </Field>
          <p className="small muted">
            ADF and KPSS determine d. Disagreement uses d = 1 with a d = 0
            sensitivity row in the ARIMA output. Seasonal AR/MA terms are
            allowed only for monthly NSA data; seasonal differencing is zero.
          </p>
          {p.order_selection === "fixed" && (
            <div className="two-fields">
              {number("p", "AR order p", 1, 0, 4)}
              {number("d", "Difference order d", 1, 0, 1)}
              {number("q", "MA order q", 0, 0, 4)}
              {config.frequency === "M" && (
                <>
                  {number("seasonal_p", "Seasonal AR order P", 0, 0, 1)}
                  {number("seasonal_q", "Seasonal MA order Q", 0, 0, 1)}
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
