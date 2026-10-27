import { afterEach, describe, expect, it, vi } from "vitest";
import { routeFromHash, screenHash } from "../src/navigation";
import {
  readRecentResults,
  rememberResult,
  recentResultsKey,
} from "../src/recentResults";
import type { AnalysisConfig } from "../src/types";
afterEach(() => vi.unstubAllGlobals());
const config = (seed = 1) =>
  ({
    schema_version: 1,
    snapshot_id: "fixed-snapshot",
    countries: ["CAN"],
    frequency: "Q",
    seed,
    sample: { start: "1999-Q1", end: "latest" },
    series: [{ concept_id: "cpi", role: "dependent", transform: "yoy_pct" }],
    aggregation: { cpi: "mean" },
    special_periods: { covid: "dummies" },
    model: { id: "sing.ols", params: { lags: 4 } },
    identification: null,
    outputs: {},
    comparison: { enabled: true },
  }) as AnalysisConfig;
describe("navigation compatibility", () => {
  it.each(["#models", "#library"])(
    "%s opens the full library inside Build",
    (hash) => {
      expect(routeFromHash(hash)).toEqual({
        screen: "builder",
        methodsOpen: true,
      });
    },
  );
  it.each([
    "#methods",
    "#about",
    "#source-terms",
    "#models-methods",
    "#methods-validation",
    "#diagnostic-rules",
  ])("%s retains About and its existing anchors", (hash) => {
    expect(routeFromHash(hash)).toEqual({
      screen: "methods",
      methodsOpen: false,
    });
  });
  it("retains every old screen route and ignores arbitrary document anchors", () => {
    for (const name of ["home", "builder", "data", "catalogue", "results"])
      expect(routeFromHash("#" + name)?.screen).toBe(name);
    expect(routeFromHash("#templates")?.screen).toBe("home");
    expect(routeFromHash("#main-content")).toBeNull();
    expect(routeFromHash("#not-a-screen")).toBeNull();
    expect(screenHash("library")).toBe("models");
    expect(screenHash("methods")).toBe("about");
  });
});
describe("recent result configurations", () => {
  it("keeps five exact configurations, deduplicates reruns, and does not mutate inputs", () => {
    const setItem = vi.fn();
    vi.stubGlobal("localStorage", { setItem });
    const original = config();
    let entries = rememberResult([], original, "2026-10-27T10:00:00Z");
    expect(entries[0].config).toEqual(original);
    expect(entries[0].config).not.toBe(original);
    original.seed = 9;
    expect(entries[0].config.seed).toBe(1);
    for (let i = 2; i <= 7; i++) entries = rememberResult(entries, config(i));
    expect(entries.map((e) => e.config.seed)).toEqual([7, 6, 5, 4, 3]);
    const before = structuredClone(entries);
    const rerun = rememberResult(entries, config(4));
    expect(entries).toEqual(before);
    expect(rerun.map((e) => e.config.seed)).toEqual([4, 7, 6, 5, 3]);
    expect(setItem).toHaveBeenLastCalledWith(
      recentResultsKey,
      JSON.stringify(rerun),
    );
  });
  it("keeps a session list when reads and writes throw", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw Error("blocked");
      },
      setItem: () => {
        throw Error("quota");
      },
    });
    expect(readRecentResults(() => true)).toEqual([]);
    expect(rememberResult([], config())[0].config).toEqual(config());
  });
  it("ignores malformed storage and configurations rejected by the schema", () => {
    let raw = "{";
    vi.stubGlobal("localStorage", { getItem: () => raw });
    expect(readRecentResults(() => true)).toEqual([]);
    raw = JSON.stringify([
      { config: config(), completedAt: "2026-10-27T10:00:00Z" },
      { config: { seed: 9 }, completedAt: "2026-10-27T10:00:00Z" },
      null,
      { config: config(), completedAt: "not-a-date" },
    ]);
    const valid = vi.fn((x: unknown) =>
      Boolean(x && typeof x === "object" && "snapshot_id" in x),
    );
    expect(readRecentResults(valid)).toHaveLength(1);
    raw = " ".repeat(1_000_001);
    expect(readRecentResults(valid)).toEqual([]);
  });
});
