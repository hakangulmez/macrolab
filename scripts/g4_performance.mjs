/* Real production UI timing; the caller owns and stops the loopback server. */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import os from "node:os";
import { execFileSync } from "node:child_process";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const require = createRequire(import.meta.url);
const { chromium } = require("../web/node_modules/@playwright/test");
const base = process.env.G4_BASE_URL ?? "http://127.0.0.1:8765/";
assert.equal(new URL(base).hostname, "127.0.0.1");
const origin = new URL(base).origin;
const output = join(root, "runs/g4");
await mkdir(output, { recursive: true });
process.env.TMPDIR = join(root, ".cache/tmp");
const tokens = JSON.parse(
  execFileSync(
    join(root, ".venv/bin/python"),
    [
      "-c",
      `
import json
from pathlib import Path
from macrolab.analysis.config import encode_config
config = json.loads(Path("configs/templates/monetary_policy.json").read_text())
config["outputs"]["irf"]["draws"] = 500
print(json.dumps({"draws_500": encode_config(config)}))
`,
    ],
    { cwd: root, encoding: "utf8" },
  ),
);
await writeFile(
  join(output, "benchmark-configs.json"),
  JSON.stringify(tokens, null, 2) + "\n",
);
const report = {
  protocol:
    "Production UI; new contexts for initial render and Builder warming; 20 sequential warm 200-draw click-to-chart runs; linear-interpolated p90; no concurrent test suite",
  environment: {
    platform: os.platform(),
    arch: os.arch(),
    cpu: os.cpus()[0].model,
    memory_bytes: os.totalmem(),
    node: process.version,
  },
  fresh_contexts: [],
  warm_200: [],
  warm_500: [],
  server: [],
  external_requests: [],
  page_errors: [],
};
const browser = await chromium.launch({
  executablePath: join(root, "scripts/local_chrome.sh"),
  headless: true,
});
const deadline = setTimeout(() => void browser.close(), 300000);
async function context() {
  const ctx = await browser.newContext({
    serviceWorkers: "block",
    viewport: { width: 1440, height: 1000 },
  });
  await ctx.route("**/*", async (route) => {
    const url = route.request().url();
    if (new URL(url).origin !== origin) {
      report.external_requests.push(url);
      await route.abort("blockedbyclient");
    } else await route.continue();
  });
  await ctx.addInitScript(() => {
    window.__g4Results = [];
    window.__g4WorkerCount = 0;
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        window.__g4WorkerCount += 1;
        this.addEventListener("message", (e) => {
          if (e.data?.result?.config_hash && e.data.result.results)
            window.__g4Results.push(e.data.result);
        });
      }
    };
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => report.page_errors.push(String(e)));
  return { ctx, page };
}
async function ready(page) {
  await page.waitForFunction(
    () =>
      document.getElementById("main-content")?.dataset.runtimeStatus ===
      "ready",
    undefined,
    { timeout: 120000 },
  );
}
async function run(page, draws) {
  const count = await page.evaluate(() => window.__g4Results.length);
  const started = performance.now();
  await page.getByTestId("run-analysis").click();
  await page.waitForFunction((n) => window.__g4Results.length > n, count, {
    timeout: 120000,
  });
  await page.getByTestId("screen-results").waitFor({ state: "visible" });
  await page
    .getByTestId("result-chart")
    .first()
    .locator("canvas,svg")
    .first()
    .waitFor({ state: "visible" });
  const wall_ms = performance.now() - started;
  const result = await page.evaluate(() => window.__g4Results.at(-1));
  assert.equal(result.status, "ok");
  assert.equal(result.config.outputs.irf.draws, draws);
  assert.deepEqual(result.config.comparison.scenarios, [
    "extended_var",
    "lag_criteria",
    "covid_include",
    "end_2019",
  ]);
  const country = result.results[0];
  const variants = country.sensitivity.variants.map((v) => ({
    id: v.variant_id,
    status: v.status,
  }));
  return {
    wall_ms,
    engine_ms: result.runtime_ms,
    config_hash: result.config_hash,
    sample: {
      start: country.actual_sample.start,
      end: country.actual_sample.end,
      nobs: country.actual_sample.nobs,
    },
    variants,
    worker_count: await page.evaluate(() => window.__g4WorkerCount),
  };
}
function summarize(rows) {
  const values = rows.map((r) => r.wall_ms).sort((a, b) => a - b);
  const percentile = (p) => {
    const x = (values.length - 1) * p;
    const lo = Math.floor(x);
    return values[lo] + (values[Math.ceil(x)] - values[lo]) * (x - lo);
  };
  return {
    repetitions: values.length,
    median_ms: percentile(0.5),
    p90_ms: percentile(0.9),
    minimum_ms: values[0],
    maximum_ms: values.at(-1),
  };
}
try {
  for (let i = 0; i < 3; i += 1) {
    const { ctx, page } = await context();
    const start = performance.now();
    await page.goto(base);
    await page.getByTestId("screen-home").waitFor({ state: "visible" });
    const meaningful_render_ms = performance.now() - start;
    const home = await page.evaluate(() => ({
      workers: window.__g4WorkerCount,
      scripts: performance
        .getEntriesByType("resource")
        .filter((r) => /\.m?js(?:\?|$)/.test(r.name))
        .map((r) => ({
          url: new URL(r.name).pathname,
          bytes: r.encodedBodySize,
        })),
    }));
    assert.equal(
      home.workers,
      0,
      "Home should not eagerly load scientific Python",
    );
    const warmStart = performance.now();
    await page.getByTestId("template-monetary_policy").click();
    await ready(page);
    const prewarm_ms = performance.now() - warmStart;
    assert.equal(await page.evaluate(() => window.__g4WorkerCount), 1);
    const initial_run = await run(page, 200);
    report.fresh_contexts.push({
      meaningful_render_ms,
      prewarm_ms,
      home,
      initial_run,
    });
    if (i === 2) {
      for (let j = 0; j < 20; j += 1) {
        await page
          .getByRole("button", { name: "← Edit this analysis" })
          .click();
        await ready(page);
        const result = await run(page, 200);
        assert.equal(result.worker_count, 1, "Warm runs must reuse one worker");
        report.warm_200.push(result);
        console.log(
          `200 draws ${j + 1}/20: ${result.wall_ms.toFixed(1)} ms click-to-chart`,
        );
      }
      await page.goto(
        `${base}?c=${encodeURIComponent(tokens.draws_500)}#builder`,
      );
      await ready(page);
      for (let j = 0; j < 5; j += 1) {
        if (j)
          await page
            .getByRole("button", { name: "← Edit this analysis" })
            .click();
        report.warm_500.push(await run(page, 500));
      }
      const manifest = await page.evaluate(async () =>
        (await fetch("/data/manifest.json")).json(),
      );
      for (const template of manifest.templates) {
        const start = performance.now();
        const response = await page.request.post(`${origin}/run`, {
          data: template.config,
          timeout: 120000,
        });
        assert.equal(response.status(), 200);
        const result = await response.json();
        assert.equal(result.status, "ok");
        report.server.push({
          template: template.id,
          wall_ms: performance.now() - start,
          engine_ms: result.runtime_ms,
          config_hash: result.config_hash,
        });
      }
    }
    await ctx.close();
  }
  report.browser_version = browser.version();
  report.summary = {
    warm_200: summarize(report.warm_200),
    warm_500: summarize(report.warm_500),
  };
  report.passed =
    !report.external_requests.length && !report.page_errors.length;
  await writeFile(
    join(output, "performance.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  assert(report.passed);
  console.log(JSON.stringify(report.summary));
} finally {
  clearTimeout(deadline);
  await browser.close();
}
