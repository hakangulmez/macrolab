import type {
  AnalysisConfig,
  AnalysisResult,
  Manifest,
  SeriesSpec,
} from "./types";
import { record, text } from "./format";
import { countryIndicators } from "./displayLabels";

function seriesName(
  spec: SeriesSpec,
  config: AnalysisConfig,
  manifest: Manifest,
) {
  const labels: Record<string, string> = {
    gdp_real: "real GDP",
    unemp: "unemployment rate",
    oil_brent: "Brent oil price",
    neer: "NEER",
    rate_3m: "3-month rate",
    commod_idx: "non-fuel commodity index",
    identified_impulse: "identified ECB shock",
  };
  const label =
    spec.concept_id === "cpi"
      ? (countryIndicators(manifest.indicators, config.countries[0])
          .find((i) => i.concept_id === "cpi")
          ?.title.split(" · ")[0] ?? "consumer prices")
      : spec.concept_id === "policy_rate"
        ? config.model.params.policy_measure === "dfr" ||
          config.model.params.first_stage_source === "ecb_dfr"
          ? "ECB DFR"
          : "policy rate"
        : (labels[spec.concept_id] ??
          manifest.indicators.find((i) => i.concept_id === spec.concept_id)
            ?.title ??
          spec.concept_id);
  const transforms: Record<string, string> = {
    level: label,
    log: `log(${label})`,
    diff: `Δ ${label}`,
    log_diff: `100 Δ log(${label})`,
    yoy_pct: `y/y ${label} growth`,
    yoy_diff: `y/y change in ${label}`,
    qoq_saar: `q/q annualised ${label} growth`,
    hp_cycle: `HP gap(${spec.transform_params?.log ? "log " : ""}${label}, λ=${text(spec.transform_params?.lamb, "1600")})`,
    hamilton_cycle: `Hamilton gap(${label})`,
    index_to_base: `rebased ${label}`,
  };
  return transforms[spec.transform] ?? `${spec.transform}(${label})`;
}
/** Equation labels are presentation only; returned config remains authoritative. */
export function resultSpecification(
  result: AnalysisResult,
  manifest: Manifest,
) {
  const config = result.config,
    p = config.model.params,
    id = config.model.id,
    r = result.results[0];
  const name = (s: SeriesSpec) => seriesName(s, config, manifest);
  const endogenous = config.series.filter((s) =>
    ["endogenous", "shock"].includes(s.role),
  );
  const responses = config.series.filter((s) =>
    ["response", "dependent"].includes(s.role),
  );
  const regressors = config.series.filter((s) =>
    ["regressor", "exogenous"].includes(s.role),
  );
  const controls = config.series.filter((s) => s.role === "exogenous");
  const actualTerms = (r?.coefficients_table ?? []).map((c) => c.term);
  const nuisance = [
    ...new Set(
      actualTerms.filter((term) => /^(covid_|season_|crisis_)/.test(term)),
    ),
  ];
  const covid = config.special_periods.covid === "dummy";
  const extra = nuisance.length ? ` + δ′ Dₜ` : covid ? " + δ′ COVIDₜ" : "";
  const constant =
    p.effects === "two_way"
      ? "αᵢ + τₜ"
      : id.startsWith("panel.")
        ? "αᵢ"
        : p.trend === "n"
          ? "0"
          : "α";
  const lag = text(p.lags, "selected");
  let equation: string;
  const definitions: string[] = [];
  if (
    id === "sing.ols" ||
    id === "sing.ardl" ||
    id === "sing.rolling" ||
    id === "panel.fe"
  ) {
    const rhs = regressors.map((s, i) => `β${i + 1} ${name(s)}ₜ`).join(" + ");
    equation = `${responses.map(name).join(", ")}ₜ = ${constant}${rhs ? ` + ${rhs}` : ""}${id === "sing.ardl" ? " + lagged dependent variable and regressors" : ""}${Number(p.dependent_lags) > 0 ? ` + Σⱼ₌₁…${text(p.dependent_lags)} ρⱼ ${responses.map(name).join(", ")}ₜ₋ⱼ` : ""}${extra} + εₜ`;
    if (id === "panel.fe")
      definitions.push(
        "All variables and errors carry country index i; country intercepts are absorbed.",
      );
    if (id === "sing.rolling")
      definitions.push(
        "The equation is re-estimated within each selected rolling window.",
      );
  } else if (["lp.ols", "panel.lp", "cmp.common_shock"].includes(id)) {
    const response = responses[0],
      mode = text(
        record(p.response_modes)[response?.concept_id] ?? p.response_mode,
        "level",
      );
    const y = response ? name(response) : "selected response";
    const target =
      mode === "cumulative_log"
        ? `100 [${y}ₜ₊ₕ − ${y}ₜ₋₁]`
        : mode === "change"
          ? `[${y}ₜ₊ₕ − ${y}ₜ₋₁]`
          : mode === "growth_log"
            ? `100 × ${text(p.growth_scale, "1")} [${y}ₜ₊ₕ − ${y}ₜ₊ₕ₋₁]`
            : `${y}ₜ₊ₕ`;
    const impulse = config.series.find((s) => s.role === "shock");
    const totalLags = Number(p.lags ?? 2) + Number(Boolean(p.lag_augmented));
    equation = `${target} = ${id === "panel.lp" ? "αᵢ,ₕ" : "αₕ"} + θₕ ${impulse ? name(impulse) : "shock"}ₜ + Σⱼ₌₁…${totalLags} Γₕ,ⱼ Xₜ₋ⱼ${controls.length ? " + γₕ′ Zₜ" : ""}${extra} + εₜ₊ₕ`;
    const differences = record(p.lag_difference_scales);
    definitions.push(
      `X = (${config.series
        .filter((s) =>
          [
            "response",
            "dependent",
            "endogenous",
            "regressor",
            "shock",
          ].includes(s.role),
        )
        .map((s) =>
          differences[s.concept_id]
            ? `${text(differences[s.concept_id])} Δ ${name(s)}`
            : name(s),
        )
        .join(
          "; ",
        )}); ${text(p.lags)} lags${p.lag_augmented ? " + one augmentation lag" : ""}.`,
    );
    if (controls.length)
      definitions.push(`Z = (${controls.map(name).join("; ")}).`);
    if (id === "cmp.common_shock")
      definitions.push(
        "A separate equation is estimated for each country and response; the same stage-1 ECB shock enters each equation. Other response equations remain in Details.",
      );
    if (id === "panel.lp")
      definitions.push(
        "Variables and errors carry country index i; the common shock has only a time index. The other response equation remains in Details.",
      );
    if (p.template_id === "tur_pass_through")
      definitions.push(
        "The headline ratio divides this cumulative CPI response by the cumulative NEER response to the same impulse, horizon by horizon.",
      );
  } else if (
    [
      "var.ols",
      "bvar.minn",
      "ident.recursive",
      "ident.external_series",
      "fc.var",
    ].includes(id)
  ) {
    equation = `Yₜ = ${constant} + Σⱼ₌₁…${lag} Aⱼ Yₜ₋ⱼ${controls.length ? " + B Zₜ" : ""}${extra} + uₜ`;
    const order = config.identification?.params.order;
    const ordered = order?.length
      ? order.flatMap((key) => endogenous.filter((s) => s.concept_id === key))
      : endogenous;
    definitions.push(`Y = (${ordered.map(name).join("; ")}).`);
    if (controls.length)
      definitions.push(`Z = (${controls.map(name).join("; ")}).`);
    if (id === "bvar.minn")
      definitions.push(
        "Conjugate Minnesota prior; posterior inference uses the settings in the original result.",
      );
  } else if (id === "fc.eval") {
    const target =
      config.series.find(
        (s) => s.concept_id === record(r?.evaluation).target,
      ) ?? config.series[0];
    equation = `ŷₜ₊ₕ|ₜ⁽ᵐ⁾ = fₘ(${name(target)}₁:ₜ, X₁:ₜ); m ∈ {${Array.isArray(record(r?.evaluation).models) ? (record(r?.evaluation).models as unknown[]).join(", ") : "reported models"}}`;
    definitions.push(
      `y = ${name(target)}; BVAR vector X = (${config.series.map(name).join("; ")}). Each model is fitted using only its origin's training prefix; this is a model comparison, not one pooled estimating equation.`,
    );
  } else if (id === "uni.arima") {
    equation = `φ(L)(1 − L)ᵈ ${config.series.map(name).join(", ")}ₜ = c + θ(L)εₜ`;
    definitions.push(
      "Selected ordinary and any seasonal orders are reported in the original ARIMA details.",
    );
  } else if (id === "vecm" || id === "test.coint") {
    equation = `Δ Yₜ = α β′ Yₜ₋₁ + Σⱼ Γⱼ Δ Yₜ₋ⱼ + deterministic terms + uₜ`;
    definitions.push(
      `Y = (${config.series.map(name).join("; ")}); rank and deterministic case are shown in the original test or VECM details.`,
    );
  } else if (id.startsWith("filter.")) {
    equation = `${config.series.map(name).join(", ")}ₜ = trendₜ + cycleₜ`;
  } else if (id === "out.hd") {
    equation = `${config.series.map(name).join(", ")}ₜ = initial conditions + deterministic component + Σₖ shock contributionₖ,ₜ`;
  } else {
    equation = `${manifest.models.find((m) => m.id === id)?.title ?? id}(${config.series.map(name).join("; ")})`;
    definitions.push(
      "This output is a descriptive or testing operation; its statistic and assumptions are shown in the original details.",
    );
  }
  if (nuisance.length)
    definitions.push(
      `D = (${nuisance.map((term) => term.replace("covid_", "COVID dummy ").replace("season_", "Seasonal indicator ").replace("crisis_", "Crisis indicator ")).join("; ")}); exact indicators and coefficients remain in the original details and exports.`,
    );
  else if (covid)
    definitions.push(
      `COVID indicators: ${config.special_periods.covid_window?.start ?? "configured start"}–${config.special_periods.covid_window?.end ?? "configured end"}; only active columns are retained.`,
    );
  const seasonal =
    record(r?.local_projection).seasonal_controls ??
    record(r?.panel).seasonal_controls;
  const seasonalGroups = record(seasonal).columns
    ? [record(seasonal)]
    : Object.values(record(seasonal)).map(record);
  const seasonalColumns = [
    ...new Set(
      seasonalGroups.flatMap((group) =>
        Array.isArray(group.columns) ? group.columns.map(String) : [],
      ),
    ),
  ];
  if (
    seasonalColumns.length &&
    !nuisance.some((term) => term.startsWith("season_"))
  ) {
    equation = equation.replace(/ \+ ε/, " + s′ Sₜ + ε");
    definitions.push(
      `S = (${seasonalColumns.map((column) => `${config.frequency === "M" ? "month" : "quarter"} ${column.slice(7)} indicator`).join("; ")}); calendar seasonality controls, with the first period as reference.`,
    );
  }
  const covariance =
    record(r?.panel).covariance ??
    record(r?.local_projection).covariance ??
    r?.coefficients_table?.[0]?.covariance ??
    p.covariance;
  const inference = covariance
    ? `${text(covariance)}${covariance === "HAC" && p.hac_lags !== undefined ? `(${text(p.hac_lags)})` : ""}`
    : r?.irf
      ? `${r.irf.band_method} · ${Math.round(r.irf.band_level * 100)}% pointwise bands`
      : id === "fc.eval"
        ? "paired loss comparisons; DM/HLN"
        : "see original method details";
  const settings = `${manifest.models.find((m) => m.id === id)?.title ?? id} · ${inference} · lags ${text(p.lags ?? p.dependent_lags, "not applicable")} · ${r?.actual_sample.start}–${r?.actual_sample.end} · n = ${r?.actual_sample.nobs}`;
  return { equation, definitions, settings };
}
