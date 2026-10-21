import { afterEach, describe, expect, it, vi } from "vitest";
import { createHash, webcrypto } from "node:crypto";
import type { AnalysisConfig } from "../src/types";

afterEach(() => vi.unstubAllGlobals());
describe("sensitivity inputs reach the real worker and export", () => {
  it("includes the declared extended VAR inputs without making them baseline series", async () => {
    vi.resetModules();
    vi.stubGlobal("location", {
      href: "http://127.0.0.1:5173/",
      origin: "http://127.0.0.1:5173",
    });
    vi.stubGlobal("crypto", webcrypto);
    const country = {
      snapshot_id: "fixture",
      country: { iso3: "USA" },
      cards: ["gdp_real", "reer", "credit_pnfs"].map((concept_id) => ({
        concept_id,
        status: "available",
      })),
      series: {
        gdp_real: [["2000-Q1", 100]],
        reer: [["2000-Q1", 99]],
        credit_pnfs: [["2000-Q1", 80]],
      },
    };
    const payload = JSON.stringify(country);
    const manifest = {
      snapshot_id: "fixture",
      countries: [],
      publication_approved: false,
      country_files: {
        USA: {
          url: "/country.json",
          bytes: Buffer.byteLength(payload),
          sha256: createHash("sha256").update(payload).digest("hex"),
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (url: URL) =>
          new Response(
            url.pathname === "/data/manifest.json"
              ? JSON.stringify(manifest)
              : payload,
          ),
      ),
    );
    const { buildBundle } = await import("../src/runtime");
    const config = {
      snapshot_id: "fixture",
      countries: ["USA"],
      series: [{ concept_id: "gdp_real" }],
      comparison: { enabled: true, scenarios: ["extended_var"] },
    } as AnalysisConfig;
    const bundle = await buildBundle(config);
    expect(Object.keys(bundle.countries.USA.series)).toEqual([
      "gdp_real",
      "reer",
      "credit_pnfs",
    ]);
    expect(bundle.countries.USA.series.reer.observations).toEqual([
      ["2000-Q1", 99],
    ]);
    expect(config.series).toHaveLength(1);
    const disabled = await buildBundle({
      ...config,
      comparison: { ...config.comparison, enabled: false },
    });
    expect(Object.keys(disabled.countries.USA.series)).toEqual(["gdp_real"]);
  });
});
