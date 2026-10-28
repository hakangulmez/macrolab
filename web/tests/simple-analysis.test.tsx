import { expect, it, afterEach, vi } from "vitest";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import {
  freshSimple,
  dataActionConfig,
  simpleQuestion,
  normalisedSimpleCopy,
  selectionChecks,
  simpleSummary,
  configKey,
  readBuildMode,
  saveBuildMode,
  buildModeKey,
  questions,
  type Question,
  type SimpleSelection,
} from "../src/simpleAnalysis";
import { QuestionPicker } from "../src/components/QuestionPicker";
import type { Manifest, AnalysisConfig } from "../src/types";
const countries = ["CAN", "GBR", "JPN", "DEU", "FRA", "ESP", "USA", "TUR"];
const concepts = [
  "unemp",
  "cpi",
  "gdp_real",
  "gov_debt",
  "money_broad",
  "rate_3m",
];
const m = {
  snapshot_id: "fixture",
  countries: countries.map((iso3) => ({
    iso3,
    name: iso3,
    monetary_union: ["DEU", "FRA", "ESP"].includes(iso3) ? "EA" : null,
  })),
  indicators: concepts.map((concept_id) => ({
    concept_id,
    title: concept_id,
    default_transform:
      concept_id === "cpi" || concept_id === "gdp_real" ? "yoy_pct" : "level",
    frequency:
      concept_id === "gov_debt" ? "A" : concept_id === "gdp_real" ? "Q" : "M",
  })),
  coverage: countries.flatMap((country) =>
    concepts.map((concept_id) => ({
      country,
      concept_id,
      status:
        country === "DEU" && concept_id === "money_broad"
          ? "missing"
          : "available",
      observations: country === "DEU" && concept_id === "money_broad" ? 0 : 100,
      frequency:
        concept_id === "gov_debt" ? "A" : concept_id === "gdp_real" ? "Q" : "M",
      stale: country === "TUR" && concept_id === "rate_3m",
    })),
  ),
  templates: ["phillips_curve", "monetary_policy", "same_ecb_shock"].map(
    (id) => ({
      id,
      config: JSON.parse(
        readFileSync(`../configs/templates/${id}.json`, "utf8"),
      ),
    }),
  ),
  models: [
    { id: "desc.plot", params: { properties: {} } },
    {
      id: "desc.compare",
      params: { properties: { statistic: { default: "mean" } } },
    },
    {
      id: "uni.arima",
      params: {
        properties: {
          horizon: { default: 8 },
          order_selection: { default: "aicc" },
        },
      },
    },
  ],
} as unknown as Manifest;
for (const t of m.templates) t.config.snapshot_id = m.snapshot_id;
afterEach(() => vi.unstubAllGlobals());
const completedFixture = JSON.parse(
  readFileSync("tests/fixtures/simple-completed.json", "utf8"),
) as {
  manifest: Manifest;
  cases: {
    name: string;
    question: Question;
    selection: SimpleSelection;
    fresh: AnalysisConfig;
    completed: AnalysisConfig;
  }[];
};
for (const row of completedFixture.cases)
  it(`recognises engine-completed ${row.name} without mutating either config or defaults`, () => {
    const before = JSON.stringify(completedFixture);
    const manifest = completedFixture.manifest;
    expect(freshSimple(manifest, row.question, row.selection)).toEqual(
      row.fresh,
    );
    // The expected copy comes from native validated_config and recorded
    // browser-completed configs, not the frontend implementation under test.
    expect(normalisedSimpleCopy(manifest, row.fresh)).toEqual(row.completed);
    expect(normalisedSimpleCopy(manifest, row.completed)).toEqual(
      row.completed,
    );
    expect(simpleQuestion(manifest, row.fresh)).toBe(row.question);
    expect(simpleQuestion(manifest, row.completed)).toBe(row.question);
    expect(JSON.stringify(completedFixture)).toBe(before);
  });
it("retains and rejects custom fields in both fresh and completed configurations", () => {
  const row = completedFixture.cases.find((x) => x.name === "relate-CAN")!;
  const changes: ((c: AnalysisConfig) => void)[] = [
    (c) => (c.sample.start = "2005-Q1"),
    (c) => (c.model.params.covariance = "HC1"),
    (c) => (c.model.params.confidence = 0.9),
    (c) => (c.series[0].transform = "log"),
    (c) => (c.series[0].transform_params = { log: true }),
    (c) => (c.comparison.enabled = false),
    (c) => (c.comparison.scenarios = ["end_2019"]),
    (c) => (c.model.params.unknown = { future: [1, 2] }),
    (c) => (c.model.params.hac_lags = null),
    (c) => Object.assign(c, { unknown: { future: [1, 2] } }),
  ];
  for (const original of [row.fresh, row.completed])
    for (const change of changes) {
      const c = structuredClone(original);
      change(c);
      const before = JSON.stringify(c);
      expect(simpleQuestion(completedFixture.manifest, c)).toBeNull();
      expect(JSON.stringify(c)).toBe(before);
    }
});
it("never erases custom nested first-stage fields to recognise an ECB preset", () => {
  const row = completedFixture.cases.find((x) => x.name === "shock-DEU")!;
  const changes: ((first: AnalysisConfig) => void)[] = [
    (c) => (c.model.params.lags = 4),
    (c) => (c.sample.start = "2005-Q1"),
    (c) => (c.series[0].transform = "diff"),
    (c) => c.identification!.params.order.reverse(),
    (c) => (c.comparison.enabled = true),
    (c) => (c.model.params.unknown = { nested: [1, 2] }),
    (c) => Object.assign(c, { unknown: { nested: [1, 2] } }),
  ];
  for (const original of [row.fresh, row.completed])
    for (const change of changes) {
      const c = structuredClone(original);
      change(c.model.params.first_stage as AnalysisConfig);
      const before = JSON.stringify(c);
      expect(simpleQuestion(completedFixture.manifest, c)).toBeNull();
      expect(JSON.stringify(c)).toBe(before);
    }
});
it("uses approved deterministic entries for three economies per question and the same shared picker", () => {
  for (const [question] of questions)
    for (const country of question === "shock"
      ? ["DEU", "FRA", "ESP"]
      : ["CAN", "GBR", "JPN"]) {
      const c = freshSimple(m, question, {
        countries: question === "compare" ? [country, "USA"] : [country],
        preset: "same_ecb_shock",
      });
      expect(simpleQuestion(m, c)).toBe(question);
      expect(c.countries).toContain(country);
      expect(c.snapshot_id).toBe("fixture");
      expect(configKey(c)).toBe(configKey(structuredClone(c)));
    }
  const html = renderToStaticMarkup(
    <QuestionPicker select={() => undefined} />,
  );
  for (const [, label] of questions) expect(html).toContain(label);
});
it("inherits the Phillips settings and preserves both explicit shock presets", () => {
  expect(freshSimple(m, "relate")).toEqual(m.templates[0].config);
  expect(freshSimple(m, "shock")).toEqual(m.templates[1].config);
  expect(freshSimple(m, "shock", { preset: "same_ecb_shock" })).toEqual(
    m.templates[2].config,
  );
  const c = freshSimple(m, "relate", { concepts: ["gdp_real", "unemp"] });
  expect(c.series.map((s) => s.transform)).toEqual(["yoy_pct", "level"]);
  expect(c.model.params).toEqual(m.templates[0].config.model.params);
});
it("never rewrites custom fields to represent an Advanced configuration", () => {
  const original = freshSimple(m, "relate");
  for (const change of [
    (c: AnalysisConfig) => c.seed++,
    (c: AnalysisConfig) => (c.sample.start = "2005-Q1"),
    (c: AnalysisConfig) => (c.model.params.covariance = "HC1"),
    (c: AnalysisConfig) => (c.series[0].transform = "log"),
    (c: AnalysisConfig) => (c.outputs.confidence = 0.9),
  ]) {
    const c = structuredClone(original);
    change(c);
    const bytes = JSON.stringify(c);
    expect(simpleQuestion(m, c)).toBeNull();
    expect(JSON.stringify(c)).toBe(bytes);
  }
  const c = freshSimple(m, "shock", { countries: ["CAN"] });
  expect(simpleQuestion(m, c)).toBeNull();
});
it("blocks incomplete comparisons, missing countries, stale targets and incompatible frequencies", () => {
  expect(selectionChecks(m, freshSimple(m, "compare"))[0].code).toBe(
    "entry_compare_countries",
  );
  expect(
    selectionChecks(m, freshSimple(m, "relate", { concepts: ["cpi"] }))[0].code,
  ).toBe("entry_second_variable");
  expect(
    selectionChecks(
      m,
      freshSimple(m, "compare", {
        countries: ["CAN", "DEU"],
        concepts: ["money_broad"],
      }),
    ).some((x) => x.code === "entry_missing"),
  ).toBe(true);
  expect(
    selectionChecks(
      m,
      freshSimple(m, "describe", { countries: ["TUR"], concepts: ["rate_3m"] }),
    ).some((x) => x.code === "entry_stale"),
  ).toBe(true);
  expect(
    selectionChecks(
      m,
      freshSimple(m, "relate", { concepts: ["gov_debt", "unemp"] }),
    ).some((x) => x.code === "entry_frequency"),
  ).toBe(true);
});
it("supports annual descriptive entries and names the quarterly forecast horizon", () => {
  for (const q of ["describe", "compare"] as const) {
    const c = freshSimple(m, q, {
      countries: q === "compare" ? ["CAN", "GBR"] : ["CAN"],
      concepts: ["gov_debt"],
    });
    expect(c.frequency).toBe("A");
    expect(c.sample.start).toBe("1999");
    expect(selectionChecks(m, c)).toEqual([]);
  }
  const quarterly = freshSimple(m, "forecast", { concepts: ["gdp_real"] });
  expect(quarterly.frequency).toBe("Q");
  expect(quarterly.model.params.horizon).toBe(8);
  expect(simpleSummary(m, quarterly, "forecast")).toContain("eight quarters");
  expect(simpleSummary(m, freshSimple(m, "describe"), "describe")).toContain(
    "longest contiguous sample and dropped periods",
  );
  expect(simpleSummary(m, freshSimple(m, "compare"), "compare")).toContain(
    "ranked highest to lowest",
  );
});
it("handles first visit, saved explicit preference and blocked storage safely", () => {
  const storage = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => storage.get(k),
    setItem: (k: string, v: string) => storage.set(k, v),
  });
  expect(readBuildMode()).toBe("simple");
  saveBuildMode("advanced");
  expect(readBuildMode()).toBe("advanced");
  expect(storage.get(buildModeKey)).toBe("advanced");
  vi.stubGlobal("localStorage", {
    getItem() {
      throw Error("blocked");
    },
    setItem() {
      throw Error("blocked");
    },
  });
  expect(readBuildMode()).toBe("simple");
  expect(() => saveBuildMode("advanced")).not.toThrow();
});

it("Data actions carry identifiers and parameters without changing inputs or silently filling a choice", () => {
  const bytes = JSON.stringify(m);
  for (const transform of ["level", "yoy_pct"]) {
    const params = { periods: 12 };
    for (const action of [
      "build",
      "compare",
      "relate",
      "stationarity",
    ] as const) {
      const c = dataActionConfig(m, action, "CAN", "cpi", transform, params);
      expect(c.series[0].transform).toBe(transform);
      expect(c.series[0].transform_params).toEqual(params);
      expect(c.series[0].transform_params).not.toBe(params);
      expect(c.series).toHaveLength(1);
      expect(c.countries).toEqual(["CAN"]);
      expect(c.frequency).toBe(action === "relate" ? "Q" : "M");
      if (action === "compare")
        expect(
          selectionChecks(m, c).some(
            (x) => x.code === "entry_compare_countries",
          ),
        ).toBe(true);
      if (action === "relate")
        expect(
          selectionChecks(m, c).some((x) => x.code === "entry_second_variable"),
        ).toBe(true);
      if (action === "stationarity")
        expect(c.model.id).toBe("test.adf_kpss_pp");
    }
  }
  expect(JSON.stringify(m)).toBe(bytes);
});
it("permits an explicit downward frequency conversion in Advanced without changing its configuration", () => {
  const c = freshSimple(m, "compare", { countries: ["CAN", "GBR"] });
  c.frequency = "Q";
  const before = JSON.stringify(c);
  expect(
    selectionChecks(m, c).some((x) => x.code === "entry_compare_frequency"),
  ).toBe(true);
  expect(selectionChecks(m, c, false)).toEqual([]);
  expect(JSON.stringify(c)).toBe(before);
});
