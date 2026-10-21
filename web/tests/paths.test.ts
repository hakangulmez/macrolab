import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applicationURL } from "../src/runtime";

beforeEach(() =>
  vi.stubGlobal("location", {
    href: "http://127.0.0.1:5173/macrolab/?c=configuration#builder",
    origin: "http://127.0.0.1:5173",
  }),
);
afterEach(() => vi.unstubAllGlobals());

describe("static application paths", () => {
  it("resolves relative and legacy manifest paths under the Pages project prefix", () => {
    for (const path of [
      "data/manifest.json",
      "/data/manifest.json",
      "/macrolab/data/manifest.json",
    ]) {
      expect(applicationURL(path, "/macrolab/").href).toBe(
        "http://127.0.0.1:5173/macrolab/data/manifest.json",
      );
    }
    expect(applicationURL("/runtime/pyodide/", "/macrolab/").pathname).toBe(
      "/macrolab/runtime/pyodide/",
    );
  });
  it("keeps existing root-hosted local data paths unchanged", () => {
    expect(applicationURL("/data/manifest.json", "/").pathname).toBe(
      "/data/manifest.json",
    );
    expect(
      applicationURL("http://127.0.0.1:5173/macrolab/data/x.json", "/macrolab/")
        .pathname,
    ).toBe("/macrolab/data/x.json");
  });
  it("refuses external origins and escapes outside the application prefix", () => {
    for (const path of [
      "https://example.com/data.json",
      "//example.com/data.json",
      "../private.json",
      "%2e%2e/private.json",
      "http://127.0.0.1:5173/private.json",
    ]) {
      expect(() => applicationURL(path, "/macrolab/")).toThrow(
        "Only assets within this application",
      );
    }
  });
});
