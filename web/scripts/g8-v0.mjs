/* global window */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, extname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
process.env.TMPDIR = join(root, ".cache/tmp");
const out = join(root, "runs/g8");
const fixture = JSON.parse(
  await readFile(join(root, "runs/g6/browser-fixture.json")),
);
const wheel = JSON.parse(await readFile(join(out, "runtime_wheel.json")));
const lock = JSON.parse(
  await readFile(join(root, "web/runtime/assets.lock.json")),
);
const report = {
  passed: false,
  cases: [],
  v0: [],
  external_requests: [],
  errors: [],
  progress: [],
  performance: {},
};
const mime = {
  ".html": "text/html",
  ".mjs": "text/javascript",
  ".js": "text/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
};
const mounts = {
  "/runtime/": join(root, "web/runtime"),
  "/assets/": join(root, ".cache/pyodide", lock.pyodide_version),
  "/artifacts/": out,
};
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const prefix = Object.keys(mounts).find((p) => pathname.startsWith(p));
    if (!prefix) return response.writeHead(404).end();
    const file = resolve(
      mounts[prefix],
      decodeURIComponent(pathname.slice(prefix.length)),
    );
    if (!file.startsWith(mounts[prefix] + "/"))
      return response.writeHead(403).end();
    let bytes = await readFile(file);
    if (pathname.endsWith("harness.html"))
      bytes = Buffer.from(
        bytes
          .toString()
          .replace(
            'if (data.type === "log") {',
            'if (data.type === "progress") { window.runtimeProgress.push(data); return; } if (data.type === "log") {',
          )
          .replace(
            "window.runtimeLogs = [];",
            "window.runtimeLogs = []; window.runtimeProgress = [];",
          ),
      );
    response
      .writeHead(200, {
        "Content-Type": mime[extname(file)] ?? "application/octet-stream",
        "Cache-Control": "no-store",
      })
      .end(bytes);
  } catch {
    response.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const origin = `http://127.0.0.1:${server.address().port}`;
function compare(a, b, tolerance) {
  let maximum = 0,
    count = 0;
  function visit(x, y, path = "$") {
    if (typeof x === "number" && typeof y === "number") {
      const difference = Math.abs(x - y);
      count++;
      maximum = Math.max(maximum, difference);
      assert(
        Number.isFinite(difference) && difference <= tolerance,
        `${path}: ${x} vs ${y}`,
      );
    } else if (Array.isArray(x)) {
      assert(Array.isArray(y));
      assert.equal(x.length, y.length, path);
      x.forEach((v, i) => visit(v, y[i], `${path}/${i}`));
    } else if (x && typeof x === "object") {
      const keys = Object.keys(x)
        .filter((k) => k !== "runtime_ms")
        .sort();
      assert.deepEqual(
        keys,
        Object.keys(y)
          .filter((k) => k !== "runtime_ms")
          .sort(),
        path,
      );
      keys.forEach((k) => visit(x[k], y[k], `${path}/${k}`));
    } else assert.equal(x, y, path);
  }
  visit(a, b);
  return { count, maximum };
}
let browser;
try {
  browser = await chromium.launch({
    executablePath: join(root, "scripts/local_chrome.sh"),
    headless: true,
    args: [
      "--disable-background-networking",
      "--disable-component-update",
      "--no-first-run",
    ],
  });
  const context = await browser.newContext({ serviceWorkers: "block" });
  await context.route("**/*", async (route) => {
    const url = route.request().url();
    if (new URL(url).origin !== origin) {
      report.external_requests.push(url);
      await route.abort();
    } else await route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => report.errors.push(String(e)));
  await page.goto(origin + "/runtime/harness.html");
  const init = await page.evaluate(
    async ({ wheel, environment }) =>
      window.runtimeRequest({
        type: "init",
        indexURL: "/assets/",
        wheelURL: "/artifacts/" + wheel.wheel_file,
        wheelSHA256: wheel.wheel_sha256,
        codeVersion: "0.4.0",
        reproductionEnvironment: environment,
      }),
    { wheel, environment: fixture.reproduction_environment },
  );
  report.runtime = init;
  report.browser_version = browser.version();
  for (const item of fixture.v0) {
    const result = await page.evaluate(
      async (item) =>
        window.runtimeRequest({
          type: "run",
          config: item.config,
          bundle: item.bundle,
        }),
      item,
    );
    const diff = compare(item.expected, result, 0);
    await writeFile(
      join(out, "v0-" + item.id + ".browser.json"),
      JSON.stringify(result) + "\n",
    );
    report.v0.push({ id: item.id, ...diff });
    console.log("Exact v0", item.id, JSON.stringify(diff));
  }
  if (process.argv.includes("--stress")) {
    const manifest = JSON.parse(
      await readFile(join(out, "public/data/manifest.json")),
    );
    const config = structuredClone(
      manifest.templates.find((t) => t.id === "same_ecb_shock").config,
    );
    config.countries = manifest.countries
      .filter((c) => c.monetary_union === "EA" && c.iso3 !== "EA")
      .map((c) => c.iso3);
    const bundle = {
      snapshot_id: manifest.snapshot_id,
      as_of_date: manifest.as_of_date,
      countries: {},
      variants: JSON.parse(
        await readFile(join(out, "public/data/global-variants.json")),
      ).variants,
    };
    for (const code of [...config.countries, "EA"]) {
      const raw = JSON.parse(
        await readFile(join(out, "public/data/countries", code + ".json")),
      );
      bundle.countries[code] = {
        metadata: raw.country,
        series: Object.fromEntries(
          Object.entries(raw.series).map(([id, observations]) => [
            id,
            {
              metadata: raw.cards.find((c) => c.concept_id === id),
              observations,
            },
          ]),
        ),
      };
    }
    const start = Date.now();
    const result = await page.evaluate(
      async (item) => window.runtimeRequest({ type: "run", ...item }),
      { config, bundle },
    );
    report.seventeen = {
      elapsed_ms: Date.now() - start,
      status: result.status,
      countries: result.results.map((r) => ({
        country: r.country,
        status: r.status,
        n: r.actual_sample.nobs,
      })),
    };
    await writeFile(
      join(out, "ecb-seventeen.browser.json"),
      JSON.stringify(result) + "\n",
    );
    report.progress = await page.evaluate(() =>
      window.runtimeProgress.filter((p) => p.detail).map((p) => p.detail),
    );
    const cancelled = await page.evaluate(
      async (item) => {
        item.config.model.params.displayed_band = "joint";
        item.config.model.params.country_window = "common";
        item.config.model.params.bootstrap_draws = 5000;
        const pending = window.runtimeRequest({ type: "run", ...item });
        setTimeout(() => window.cancelRuntime(), 100);
        try {
          await pending;
          return false;
        } catch (e) {
          return String(e).includes("Cancelled");
        }
      },
      { config, bundle },
    );
    assert(cancelled);
    report.cancelled_without_partial_result = true;
    console.log("17-country stress", JSON.stringify(report.seventeen));
  }
  assert.equal(report.external_requests.length, 0);
  assert.equal(report.errors.length, 0);
  assert.equal(
    report.v0.reduce((sum, r) => sum + r.count, 0),
    4042,
  );
  report.passed = true;
} finally {
  await writeFile(
    join(out, "v0-browser-regression.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser?.close();
  await new Promise((r) => server.close(r));
}
