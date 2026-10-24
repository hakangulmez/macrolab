import type { AnalysisConfig, AnalysisResult } from "./types";
export const diagnosticModel = (id: string) =>
  ["test.coint", "vecm", "test.break"].includes(id);
export function breakConfig(result: AnalysisResult): AnalysisConfig | null {
  const first = result.first_stage as AnalysisResult | undefined;
  const source = first?.config ?? result.config;
  if (
    !["sing.ols", "sing.ardl", "ident.external_series"].includes(
      source.model.id,
    )
  )
    return null;
  const c = structuredClone(source),
    p = source.model.params;
  c.model = {
    id: "test.break",
    params: {
      host: source.model.id,
      source_variant: first
        ? (result.config.model.params.policy_measure ??
          (result.config.model.params.first_stage_source === "ecb_dfr"
            ? "dfr"
            : "none"))
        : "none",
      covariance: p.covariance ?? "HAC",
      hac_lags: p.hac_lags ?? (c.frequency === "M" ? 12 : 4),
      trend: p.trend ?? "c",
      lags: p.lags ?? 1,
      order: p.order ?? 1,
      break_date: "",
    },
  };
  c.comparison = { enabled: false };
  c.outputs = { confidence: 0.95 };
  return c;
}
