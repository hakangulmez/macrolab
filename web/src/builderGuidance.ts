import type { AnalysisConfig, Model } from "./types";

/** Read-only structural guidance. Scientific/data checks still run in Python. */
export function builderGuidance(
  config: AnalysisConfig,
  model: Model,
): string[] {
  if (config.model.params.template_id) return [];
  const problems: string[] = [],
    id = model.id,
    s = config.series;
  const count = (...roles: string[]) =>
    s.filter((v) => roles.includes(v.role)).length;
  const min = Number(model.inputs.min_series ?? 1),
    max = Number(model.inputs.max_series ?? 20);
  if (!config.countries.length) problems.push("Choose at least one country.");
  if (s.length < min || s.length > max)
    problems.push(
      `${model.title} needs ${min}–${max} selected indicators. Remove or add indicators explicitly.`,
    );
  if (
    (id.startsWith("sing.") ||
      id === "test.granger" ||
      (id === "test.break" &&
        config.model.params.host !== "ident.external_series") ||
      id === "panel.fe") &&
    (count("dependent") !== 1 ||
      count("regressor", ...(id === "panel.fe" ? ["exogenous"] : [])) < 1 ||
      s.some((v) => !["dependent", "regressor", "exogenous"].includes(v.role)))
  )
    problems.push(
      `${model.title} needs exactly one dependent and at least one regressor; other controls use the exogenous role.`,
    );
  if (
    ["lp.ols", "panel.lp", "cmp.common_shock"].includes(id) &&
    (count("shock") !== 1 ||
      (id === "cmp.common_shock"
        ? count("response", "dependent") < 1
        : count("response", "dependent") !== 1))
  )
    problems.push(
      `${model.title} needs one shock and ${id === "cmp.common_shock" ? "at least one response" : "exactly one response"}.`,
    );
  if (
    [
      "var.ols",
      "ident.recursive",
      "out.hd",
      "ident.external_series",
      "bvar.minn",
    ].includes(id) ||
    (id === "test.break" &&
      config.model.params.host === "ident.external_series")
  ) {
    if (
      count("endogenous", "response", "shock") < 2 ||
      s.some(
        (v) =>
          !["endogenous", "response", "shock", "exogenous"].includes(v.role),
      )
    )
      problems.push(
        "A VAR needs at least two endogenous variables (including responses and shocks); other controls use the exogenous role.",
      );
    if (id !== "var.ols" && count("shock") !== 1)
      problems.push("Choose exactly one shock variable.");
    const order = config.identification?.params.order ?? [],
      vars = s
        .filter((v) => ["endogenous", "response", "shock"].includes(v.role))
        .map((v) => v.concept_id);
    if (
      id !== "var.ols" &&
      id !== "test.break" &&
      (config.identification?.id !== "recursive" ||
        order.length !== vars.length ||
        new Set(order).size !== vars.length ||
        vars.some((v) => !order.includes(v)))
    )
      problems.push(
        "Specify an explicit recursive ordering in Identification before running.",
      );
  }
  if (
    id === "cmp.common_shock" &&
    !s.some((v) => v.concept_id === "identified_impulse" && v.role === "shock")
  )
    problems.push(
      "Use the generated first-stage shock in stage two with the explicit button below; a raw policy-rate series is not an identified impulse.",
    );
  if (id === "cmp.common_shock" && !config.model.params.first_stage)
    problems.push(
      "Choose and apply a first-stage configuration below before running the common-shock comparison.",
    );
  if (["uni.arima", "fc.var", "fc.eval"].includes(id)) {
    if (
      id === "uni.arima" &&
      count("dependent", "response", "endogenous", "shock") !== 1
    )
      problems.push(
        "ARIMA needs exactly one target. Give other selected indicators an exogenous role or remove them explicitly.",
      );
    if (
      s.some((v) => v.role === "regressor") ||
      !count("dependent", "response", "endogenous", "shock")
    )
      problems.push(
        "Forecasting needs a target (dependent/endogenous/response); other selected series use the exogenous role.",
      );
    if (
      count("exogenous") &&
      !["hold_last", "zero"].includes(String(config.model.params.future_exog))
    )
      problems.push(
        "Choose an explicit future path for exogenous controls in Forecast settings before running.",
      );
  }
  if (["test.coint", "vecm"].includes(id)) {
    if (s.some((v) => !["level", "log"].includes(v.transform)))
      problems.push(
        "Cointegration needs level or log-level inputs. Change transforms explicitly; growth rates and differences remove the long-run relationship.",
      );
    if (count("exogenous") || config.special_periods.covid !== "include")
      problems.push(
        "Johansen/VECM cannot use external or COVID dummy controls. Remove controls explicitly and choose Include for COVID.",
      );
  }
  if (
    id === "panel.lp" &&
    config.model.params.shock_type === "common" &&
    config.model.params.effects === "two_way"
  )
    problems.push(
      "Time effects absorb a common shock; choose country effects.",
    );
  return problems;
}

/** Suggestions never remove indicators or change transforms, samples or parameters. */
export function suggestedRoles(config: AnalysisConfig): AnalysisConfig | null {
  const next = structuredClone(config),
    id = config.model.id,
    active = next.series.filter((s) => s.role !== "exogenous");
  if (config.model.params.template_id || active.length < 2) return null;
  if (
    id.startsWith("sing.") ||
    ["test.granger", "panel.fe"].includes(id) ||
    (id === "test.break" &&
      config.model.params.host !== "ident.external_series")
  )
    active.forEach((s, i) => {
      s.role = i === 0 ? "dependent" : "regressor";
    });
  else if (["lp.ols", "panel.lp", "cmp.common_shock"].includes(id)) {
    const shock = active.find((s) => s.role === "shock") ?? active.at(-1)!;
    active.forEach((s, i) => {
      s.role =
        s === shock
          ? "shock"
          : i === active.findIndex((v) => v !== shock)
            ? "response"
            : "regressor";
    });
  } else if (
    [
      "var.ols",
      "ident.recursive",
      "out.hd",
      "ident.external_series",
      "bvar.minn",
    ].includes(id) ||
    (id === "test.break" &&
      config.model.params.host === "ident.external_series")
  ) {
    const shock = active.find((s) => s.role === "shock") ?? active.at(-1)!;
    active.forEach((s) => {
      s.role = s === shock ? "shock" : "endogenous";
    });
  } else if (id === "uni.arima")
    next.series.forEach((s, i) => {
      s.role = i === 0 ? "dependent" : "exogenous";
    });
  else if (["fc.var", "fc.eval"].includes(id))
    active.forEach((s) => {
      s.role = "endogenous";
    });
  else return null;
  return JSON.stringify(next.series) === JSON.stringify(config.series)
    ? null
    : next;
}

export function firstStageDraft(config: AnalysisConfig): AnalysisConfig {
  if (config.model.params.first_stage)
    return structuredClone(config.model.params.first_stage as AnalysisConfig);
  const draft = structuredClone(config);
  draft.countries = config.countries.slice(0, 1);
  draft.model = { id: "ident.recursive", params: { lags: 4 } };
  draft.comparison = { enabled: false };
  draft.identification = {
    id: "recursive",
    params: {
      order: draft.series
        .filter((s) => ["endogenous", "response", "shock"].includes(s.role))
        .map((s) => s.concept_id),
    },
  };
  return draft;
}
