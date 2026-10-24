import { countryIndicators } from "../displayLabels";
import type { AnalysisConfig, Manifest } from "../types";
import { Field, DataTable } from "./Common";
import { text } from "../format";

export function BvarControls({
  config,
  manifest,
  update,
}: {
  config: AnalysisConfig;
  manifest: Manifest;
  update: (fn: (c: AnalysisConfig) => void) => void;
}) {
  if (config.model.id !== "bvar.minn") return null;
  const p = config.model.params;
  return (
    <section className="stack" aria-label="Minnesota prior">
      <h3>Minnesota prior</h3>
      <p className="small muted">
        The conjugate prior treats own and cross-variable lags symmetrically.
        Scales come from univariate AR(p) residual standard deviations; the
        constant has a diffuse prior.
      </p>
      <Field label="Tightness selection">
        <select
          value={text(p.lambda_selection, "fixed")}
          onChange={(e) =>
            update((c) => {
              c.model.params.lambda_selection = e.target.value;
            })
          }
        >
          <option value="fixed">Fixed λ (default 0.2)</option>
          <option value="grid">Marginal-likelihood grid</option>
        </select>
      </Field>
      {p.lambda_selection === "grid" && (
        <Field label="λ grid (comma separated)">
          <input
            defaultValue={(
              (p.lambda_grid as number[]) ?? [0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5]
            ).join(", ")}
            onBlur={(e) =>
              update((c) => {
                c.model.params.lambda_grid = e.target.value
                  .split(",")
                  .map((v) => Number(v.trim()));
              })
            }
          />
        </Field>
      )}
      <Field label="Posterior draws">
        <select
          value={Number(p.draws ?? 1000)}
          onChange={(e) =>
            update((c) => {
              c.model.params.draws = Number(e.target.value);
            })
          }
        >
          <option value={1000}>1,000 seeded draws</option>
          <option value={5000}>5,000 seeded draws</option>
        </select>
      </Field>
      {[
        ["sum_of_coefficients", "Sum-of-coefficients prior"],
        ["co_persistence", "Co-persistence prior"],
        ["drop_explosive", "Exclude explosive posterior draws (reports count)"],
      ].map(([key, label]) => (
        <label className="check-row" key={key}>
          <input
            type="checkbox"
            checked={Boolean(p[key])}
            onChange={(e) =>
              update((c) => {
                c.model.params[key] = e.target.checked;
              })
            }
          />
          {label}
        </label>
      ))}
      <p className="small muted">
        Optional priors and explosive-draw exclusion are off by default. Bands
        condition on the chosen prior and any explicit stability filter.
      </p>
      <DataTable
        caption="Own first-lag prior mean, determined by transformation"
        columns={["Variable", "Transform", "Prior mean"]}
        rows={config.series
          .filter((s) => ["endogenous", "response", "shock"].includes(s.role))
          .map((s) => ({
            Variable:
              countryIndicators(manifest.indicators, config.countries[0]).find(
                (i) => i.concept_id === s.concept_id,
              )?.title ?? s.concept_id,
            Transform: s.transform,
            "Prior mean": ["level", "log", "index_to_base"].includes(
              s.transform,
            )
              ? 1
              : 0,
          }))}
      />
    </section>
  );
}
