import { expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  builderGuidance,
  suggestedRoles,
  firstStageDraft,
} from "../src/builderGuidance";
import {
  forecastViewData,
  relationshipExtent,
  relationshipEligible,
} from "../src/additionalViewData";
import { FirstStageInput } from "../src/components/FirstStageInput";
import type {
  AnalysisConfig,
  CountryResult,
  Manifest,
  Model,
} from "../src/types";
const config: AnalysisConfig = {
  schema_version: 1,
  snapshot_id: "fixture",
  countries: ["USA"],
  frequency: "Q",
  sample: { start: "1999-Q1", end: "latest" },
  aggregation: { gdp_real: "mean", cpi: "mean", policy_rate: "mean" },
  special_periods: { covid: "include" },
  series: [
    { concept_id: "gdp_real", role: "endogenous", transform: "qoq_saar" },
    { concept_id: "cpi", role: "endogenous", transform: "yoy_pct" },
    { concept_id: "policy_rate", role: "shock", transform: "level" },
  ],
  model: { id: "sing.ols", params: {} },
  identification: null,
  outputs: {},
  comparison: { enabled: false },
  seed: 1,
};
const model = (id: string) =>
  ({
    id,
    title: id,
    inputs: { min_series: 2, max_series: 6 },
  }) as unknown as Model;
it("offers roles only on explicit acceptance, without changing anything else", () => {
  const before = JSON.stringify(config);
  expect(builderGuidance(config, model("sing.ols"))).toHaveLength(1);
  const next = suggestedRoles(config)!;
  expect(next.series.map((s) => s.role)).toEqual([
    "dependent",
    "regressor",
    "regressor",
  ]);
  expect(builderGuidance(next, model("sing.ols"))).toEqual([]);
  expect(JSON.stringify(config)).toBe(before);
  expect({ ...next, series: config.series }).toEqual(config);
  const lp = { ...config, model: { id: "lp.ols", params: {} } };
  expect(suggestedRoles(lp)!.series.map((s) => s.role)).toEqual([
    "response",
    "regressor",
    "shock",
  ]);
  expect(builderGuidance(suggestedRoles(lp)!, model("lp.ols"))).toEqual([]);
  expect(
    suggestedRoles({
      ...config,
      model: { id: "sing.ols", params: { template_id: "test" } },
    }),
  ).toBeNull();
});
it("retains identification and transform barriers instead of inventing valid inputs", () => {
  expect(
    builderGuidance(
      { ...config, model: { id: "out.hd", params: {} } },
      model("out.hd"),
    ).join(" "),
  ).toContain("explicit recursive ordering");
  expect(
    builderGuidance(
      { ...config, model: { id: "test.coint", params: {} } },
      model("test.coint"),
    ).join(" "),
  ).toContain("level or log-level");
  const forecast = { ...config, model: { id: "uni.arima", params: {} } };
  const next = suggestedRoles(forecast)!;
  expect(builderGuidance(next, model("uni.arima")).join(" ")).toContain(
    "future path",
  );
  next.model.params.future_exog = "hold_last";
  expect(builderGuidance(next, model("uni.arima"))).toEqual([]);
  expect(
    builderGuidance(
      { ...config, model: { id: "cmp.common_shock", params: {} } },
      model("cmp.common_shock"),
    ).join(" "),
  ).toContain("first-stage");
});
it("hydrates picker controls without altering a saved first-stage configuration", () => {
  const first = {
    ...config,
    model: {
      id: "ident.recursive",
      params: { lags: 2, trend: "c", seasonal: true },
    },
    identification: {
      id: "recursive",
      params: { order: ["gdp_real", "cpi", "policy_rate"] },
    },
  };
  const outer = {
    ...config,
    model: { id: "cmp.common_shock", params: { first_stage: first } },
  };
  expect(firstStageDraft(outer)).toEqual(first);
  expect(firstStageDraft(outer)).not.toBe(first);
  const manifest = {
    countries: [{ iso3: "USA", name: "United States" }],
    indicators: config.series.map((s) => ({
      concept_id: s.concept_id,
      title: s.concept_id,
    })),
    models: [model("ident.recursive")],
  } as Manifest;
  const html = renderToStaticMarkup(
    <FirstStageInput config={outer} manifest={manifest} update={() => {}} />,
  );
  expect(html).toContain("First-stage country");
  expect(html).toContain("Apply first-stage configuration");
  expect(html).toContain("Advanced: first-stage JSON");
  expect(html).toContain("first-stage-editor");
  expect(html).toContain("Move first-stage gdp_real later");
  expect(html).toContain("Move first-stage Policy rate earlier");
  expect(html).not.toContain("First-stage role:");
  expect(html).not.toContain("details open");
  expect(firstStageDraft(outer)).toEqual(first);
});
it("adds forecast views by projecting stored predictions and metrics, never refitting or filling missing targets", () => {
  const result = {
    status: "ok",
    evaluation: {
      models: ["Random walk", "ARIMA"],
      predictions: [
        {
          target: "2020-Q1",
          origin: "2019-Q1",
          horizon: 4,
          actual: 2,
          predictions: { "Random walk": 1, ARIMA: 2.123456789 },
        },
        {
          target: "2021-Q1",
          origin: "2020-Q4",
          horizon: 1,
          actual: 3,
          predictions: { "Random walk": 2, ARIMA: 3 },
        },
      ],
      metrics: [{ model: "ARIMA", horizon: 4, rmse: 0.123456789 }],
    },
  } as unknown as CountryResult;
  const before = JSON.stringify(result),
    view = forecastViewData(result, 4);
  expect(view.rows).toEqual([
    {
      Period: "2020-Q1",
      Origin: "2019-Q1",
      Actual: 2,
      "Random walk": 1,
      ARIMA: 2.123456789,
    },
  ]);
  expect(view.metrics[0].rmse).toBe(0.123456789);
  expect(JSON.stringify(result)).toBe(before);
  const c = {
    ...config,
    series: [
      { concept_id: "cpi", role: "dependent", transform: "yoy_pct" },
      { concept_id: "unemp", role: "regressor", transform: "level" },
    ],
  };
  expect(
    relationshipEligible(c, {
      model_id: "sing.ols",
      status: "ok",
    } as CountryResult),
  ).toBe(true);
  expect(
    relationshipEligible(config, {
      model_id: "sing.ols",
      status: "ok",
    } as CountryResult),
  ).toBe(false);
});

it("keeps valid first-stage VAR-hosted break diagnostics runnable", () => {
  const c = {
    ...config,
    model: { id: "test.break", params: { host: "ident.external_series" } },
  };
  expect(builderGuidance(c, model("test.break"))).toEqual([]);
  expect(suggestedRoles(c)).toBeNull();
});

it("rounds scatter bounds outward without changing inputs or forcing zero", () => {
  const values = [5.033333333333333, 13.5];
  const original = [...values];
  expect(relationshipExtent(values)).toEqual({ min: 4, max: 14, step: 2 });
  expect(values).toEqual(original);
  expect(relationshipExtent([-3.2, 3.3])).toEqual({ min: -4, max: 4, step: 2 });
  expect(relationshipExtent([-14, -4]).max).toBeLessThan(0);
  expect(relationshipExtent([1000, 1001])).toEqual({
    min: 999.75,
    max: 1001.25,
    step: 0.25,
  });
  expect(relationshipExtent([0, 0])).toEqual({
    min: -0.06,
    max: 0.06,
    step: 0.02,
  });
  expect(relationshipExtent([...values, Number.NaN])).toEqual(
    relationshipExtent(values),
  );
});
