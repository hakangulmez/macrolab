import type { AnalysisConfig, Indicator, Manifest, SeriesSpec } from "./types";

const systemModels = [
  "var.ols",
  "ident.recursive",
  "out.hd",
  "ident.external_series",
  "bvar.minn",
  "fc.var",
  "fc.eval",
  "test.coint",
  "vecm",
];
export const shockModels = [
  "ident.recursive",
  "out.hd",
  "ident.external_series",
  "bvar.minn",
  "lp.ols",
  "panel.lp",
  "cmp.common_shock",
];
export function flowY(c: AnalysisConfig): SeriesSpec | undefined {
  const series = c.series.filter((s) => s.concept_id !== "identified_impulse");
  return (
    series.find((s) => s.role === "dependent") ??
    series.find((s) => s.role === "response") ??
    series.find((s) => !["shock", "exogenous"].includes(s.role)) ??
    series[0]
  );
}
export function blankAnalysis(m: Manifest): AnalysisConfig {
  return {
    schema_version: 1,
    snapshot_id: m.snapshot_id,
    countries: [],
    series: [],
    frequency: "Q",
    aggregation: {},
    sample: { start: "1999-Q1", end: "latest" },
    special_periods: { covid: "include" },
    model: { id: "sing.ols", params: {} },
    identification: null,
    outputs: { confidence: 0.95 },
    comparison: { enabled: false },
    seed: 20261021,
  };
}
/** Preserve the relative order already chosen; append only newly included variables. */
export function reconcileOrder(c: AnalysisConfig) {
  if (!c.identification) return;
  const ids = c.series
    .filter((s) => ["endogenous", "response", "shock"].includes(s.role))
    .map((s) => s.concept_id);
  c.identification.params.order = [
    ...c.identification.params.order.filter((id) => ids.includes(id)),
    ...ids.filter((id) => !c.identification!.params.order.includes(id)),
  ];
}
function xRole(c: AnalysisConfig) {
  return c.model.id === "uni.arima"
    ? "exogenous"
    : systemModels.includes(c.model.id)
      ? "endogenous"
      : c.model.id.startsWith("sing.") ||
          [
            "test.granger",
            "test.break",
            "panel.fe",
            "lp.ols",
            "panel.lp",
            "cmp.common_shock",
          ].includes(c.model.id)
        ? "regressor"
        : "endogenous";
}
function yRole(c: AnalysisConfig) {
  return c.model.id.startsWith("sing.") ||
    ["uni.arima", "test.granger", "test.break", "panel.fe"].includes(c.model.id)
    ? "dependent"
    : "response";
}
function spec(i: Indicator, role: string): SeriesSpec {
  return {
    concept_id: i.concept_id,
    role,
    transform: i.default_transform ?? "level",
    transform_params: {},
  };
}
/** Explicit edits only. Rendering and switching modes never normalise a configuration. */
export function chooseY(
  config: AnalysisConfig,
  indicator: Indicator,
): AnalysisConfig {
  const c = structuredClone(config),
    previous = flowY(c);
  if (previous?.concept_id === indicator.concept_id) return c;
  const existing = c.series.find((s) => s.concept_id === indicator.concept_id);
  if (existing) {
    if (previous) previous.role = existing.role;
    existing.role = yRole(c);
    c.series = [existing, ...c.series.filter((s) => s !== existing)];
  } else {
    c.series = [
      spec(indicator, yRole(c)),
      ...c.series.filter((s) => s !== previous),
    ];
    if (previous) delete c.aggregation[previous.concept_id];
    c.aggregation[indicator.concept_id] = "mean";
  }
  reconcileOrder(c);
  return c;
}
export function addFlowX(
  config: AnalysisConfig,
  indicator: Indicator,
): AnalysisConfig {
  const c = structuredClone(config);
  if (!c.series.some((s) => s.concept_id === indicator.concept_id)) {
    c.series.push(
      spec(
        indicator,
        indicator.scope === "global" && systemModels.includes(c.model.id)
          ? "exogenous"
          : xRole(c),
      ),
    );
    c.aggregation[indicator.concept_id] = "mean";
    reconcileOrder(c);
  }
  return c;
}
export function removeFlowX(
  config: AnalysisConfig,
  id: string,
): AnalysisConfig {
  const c = structuredClone(config);
  c.series = c.series.filter((s) => s.concept_id !== id);
  delete c.aggregation[id];
  reconcileOrder(c);
  return c;
}
export function chooseShock(
  config: AnalysisConfig,
  id: string,
): AnalysisConfig {
  const c = structuredClone(config),
    y = flowY(c)?.concept_id;
  c.series.forEach((s) => {
    if (s.concept_id === id) s.role = "shock";
    else if (s.role === "shock")
      s.role = s.concept_id === y ? yRole(c) : xRole(c);
  });
  reconcileOrder(c);
  return c;
}
/** Changing method is explicit; keep data, transforms, sample and output choices. */
export function changeFlowModel(
  config: AnalysisConfig,
  id: string,
): AnalysisConfig {
  const c = structuredClone(config);
  if (c.model.id === id) return c;
  const y = flowY(c)?.concept_id;
  c.model = { id, params: {} };
  c.series.forEach((s) => {
    s.role =
      s.concept_id === y
        ? yRole(c)
        : shockModels.includes(id) && s.role === "shock"
          ? "shock"
          : systemModels.includes(id) && s.role === "exogenous"
            ? "exogenous"
            : xRole(c);
  });
  if (
    [
      ...shockModels.filter(
        (id) => !["lp.ols", "panel.lp", "cmp.common_shock"].includes(id),
      ),
    ].includes(id)
  ) {
    c.identification ??= { id: "recursive", params: { order: [] } };
    reconcileOrder(c);
    c.outputs.irf ??= {
      horizon: 12,
      bands: 0.68,
      shock_size: 1,
      shock_mode: "one_sd",
      method: "bootstrap",
      draws: 200,
    };
  } else {
    c.identification = null;
    delete c.outputs.irf;
  }
  return c;
}
