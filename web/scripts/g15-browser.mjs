/* global window, Worker, document, requestAnimationFrame */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, extname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const require = createRequire(new URL("../package.json", import.meta.url));
const { chromium } = require("@playwright/test"),
  AxeBuilder = require("@axe-core/playwright").default;
const root = dirname(dirname(dirname(fileURLToPath(import.meta.url)))),
  out = resolve(root, process.env.MACROLAB_REVIEW_DIR ?? "runs/g15"),
  site = join(out, "site"),
  screens = join(
    root,
    "docs/screenshots",
    process.env.MACROLAB_SCREENSHOT_GATE ?? "g15",
  );
process.env.TMPDIR = join(root, ".cache/tmp");
await mkdir(join(out, "template-downloads"), { recursive: true });
await mkdir(screens, { recursive: true });
const ready = JSON.parse(await readFile(join(site, "data/manifest.json")));
const wheel = JSON.parse(await readFile(join(out, "runtime_wheel.json")));
assert.equal(
  ready.runtime.wheel_sha256,
  wheel.wheel_sha256,
  "Build must match current runtime source",
);
assert.equal(ready.schema_url, "schemas/analysis_config.schema.json");
const fixture = JSON.parse(await readFile(join(out, "template-fixture.json")));
const selectedCases = process.argv
  .find((arg) => arg.startsWith("--cases="))
  ?.slice(8)
  .split(",");
const report = {
  passed: false,
  cases: [],
  accessibility: [],
  external_requests: [],
  failed_requests: [],
  errors: [],
  performance: {},
  presentation: [],
};
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, "http://localhost").pathname;
    if (!path.startsWith("/macrolab/")) return res.writeHead(404).end();
    const file = resolve(
      site,
      decodeURIComponent(path.slice(10)) || "index.html",
    );
    if (!file.startsWith(site + "/")) return res.writeHead(403).end();
    res
      .writeHead(200, {
        "Content-Type":
          {
            ".html": "text/html",
            ".js": "text/javascript",
            ".mjs": "text/javascript",
            ".json": "application/json",
            ".wasm": "application/wasm",
            ".css": "text/css",
            ".svg": "image/svg+xml",
            ".woff2": "font/woff2",
          }[extname(file)] ?? "application/octet-stream",
        "Cache-Control": "no-store",
      })
      .end(await readFile(file));
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const origin = `http://127.0.0.1:${server.address().port}`;
function compare(a, b) {
  let count = 0,
    max = 0;
  function visit(x, y, p = "") {
    if (typeof x === "number") {
      assert.equal(typeof y, "number", p);
      const d = Math.abs(x - y);
      assert(d <= 1e-8, `${p}: ${x} / ${y}`);
      max = Math.max(max, d);
      count++;
    } else if (Array.isArray(x)) {
      assert.equal(x.length, y.length, p);
      x.forEach((v, i) => visit(v, y[i], p + "/" + i));
    } else if (x && typeof x === "object") {
      assert.deepEqual(Object.keys(x).sort(), Object.keys(y).sort(), p);
      for (const k of Object.keys(x))
        if (!["runtime_ms", "template_timing", "code_version"].includes(k))
          visit(x[k], y[k], p + "/" + k);
    } else assert.deepEqual(x, y, p);
  }
  visit(a, b);
  return { count, max };
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
  const context = await browser.newContext({
    serviceWorkers: "block",
    viewport: { width: 1440, height: 1000 },
  });
  await context.route("**/*", async (route) => {
    if (
      !route
        .request()
        .url()
        .startsWith(origin + "/macrolab/")
    ) {
      report.external_requests.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(90000);
  page.on("pageerror", (e) => report.errors.push(String(e)));
  page.on("response", (r) => {
    if (r.status() >= 400) report.failed_requests.push(r.url());
  });
  await page.addInitScript(() => {
    window.panelRuns = [];
    window.panelProgress = [];
    window.partialRuns = [];
    const Original = Worker;
    window.Worker = class extends Original {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", ({ data }) => {
          if (data.type === "result" && data.result?.results)
            window.panelRuns.push(data.result);
          if (data.type === "partial") window.partialRuns.push(data.result);
          if (data.type === "progress" && data.detail)
            window.panelProgress.push(data.detail);
        });
      }
    };
  });
  const quantile = (xs, q) => {
    const a = xs.toSorted((a, b) => a - b),
      x = (a.length - 1) * q,
      i = Math.floor(x);
    return a[i] + (a[Math.min(i + 1, a.length - 1)] - a[i]) * (x - i);
  };
  async function checkView(name, testId) {
    for (const width of [1440, 375]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.getByTestId(testId).waitFor();
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() => requestAnimationFrame(r)),
          ),
      );
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth + 1,
        ),
        name + " overflow",
      );
      const axe = await new AxeBuilder({ page }).analyze();
      const violations = axe.violations.filter((v) =>
        ["serious", "critical"].includes(v.impact),
      );
      report.accessibility.push({ name, width, violations });
      assert.equal(violations.length, 0, JSON.stringify(violations));
      await page
        .getByTestId(testId)
        .screenshot({ path: join(screens, `${name}-${width}.png`) });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  for (const name of selectedCases ?? Object.keys(fixture.cases)) {
    await page.goto(
      origin + "/macrolab/?c=" + encodeURIComponent(fixture.tokens[name]),
    );
    await page.getByTestId("screen-builder").waitFor();
    await page.locator('main[data-runtime-status="ready"]').waitFor();
    await checkView(name + "-builder", "screen-builder");
    const elapsed = [],
      baseline = [],
      native = JSON.parse(await readFile(join(out, name + ".json")));
    let result;
    for (let i = 0; i < Number(process.env.MACROLAB_TEMPLATE_RUNS ?? 5); i++) {
      if (i) await page.getByTestId("nav-builder").click();
      const n = await page.evaluate(() => window.panelRuns.length);
      const partial = await page.evaluate(() => window.partialRuns.length);
      const start = Date.now();
      await page.getByTestId("run-analysis").click();
      await page.waitForFunction(
        (n) => window.partialRuns.length > n,
        partial,
        { timeout: 300000 },
      );
      await page.getByTestId("v2-template-results").waitFor();
      if (name !== "ea_phillips_pooled")
        await page
          .getByTestId("v2-template-results")
          .locator("canvas")
          .first()
          .waitFor();
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() => requestAnimationFrame(r)),
          ),
      );
      baseline.push(Date.now() - start);
      await page.waitForFunction((n) => window.panelRuns.length > n, n, {
        timeout: 300000,
      });
      result = await page.evaluate(() => window.panelRuns.at(-1));
      assert.equal(result.status, "ok", JSON.stringify(result.checks));
      await page.getByTestId("cancel-analysis").waitFor({ state: "hidden" });
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() => requestAnimationFrame(r)),
          ),
      );
      elapsed.push(Date.now() - start);
    }
    await writeFile(
      join(out, name + ".browser.json"),
      JSON.stringify(result) + "\n",
    );
    const parity = compare(native, result);
    report.cases.push({ name, ...parity });
    report.performance[name] = {
      baseline_runs_ms: baseline,
      baseline_median_ms: quantile(baseline, 0.5),
      baseline_p90_ms: quantile(baseline, 0.9),
      runs_ms: elapsed,
      median_ms: quantile(elapsed, 0.5),
      p90_ms: quantile(elapsed, 0.9),
    };
    console.log(
      name,
      JSON.stringify({ ...parity, ...report.performance[name] }),
    );
    for (const kind of ["csv", "png", "python"]) {
      const event = page.waitForEvent("download", { timeout: 300000 });
      await page.getByTestId("export-" + kind).click();
      await (
        await event
      ).saveAs(
        join(
          out,
          "template-downloads",
          name + "." + (kind === "python" ? "py" : kind),
        ),
      );
    }
    await checkView(name, "screen-results");
    if (name === "same_ecb_shock_pooled") {
      assert.equal(
        await page
          .getByRole("button", {
            name: "Run break diagnostics for the ECB first-stage policy-rate equation",
            exact: true,
          })
          .count(),
        1,
      );
      await page
        .getByRole("combobox", { name: "Pooled outcome", exact: true })
        .selectOption("gdp_real");
      assert.match(await page.getByTestId("panel-results").innerText(), /GDP/);
      await checkView(name + "-gdp", "screen-results");
      const event = page.waitForEvent("download");
      await page.getByTestId("export-png").click();
      await (
        await event
      ).saveAs(join(out, "template-downloads", name + "-gdp.png"));
      const panel = page.waitForEvent("download");
      await page
        .getByRole("combobox", { name: "PNG scope", exact: true })
        .selectOption("panel");
      await page.getByTestId("export-png").click();
      await (
        await panel
      ).saveAs(join(out, "template-downloads", name + "-both.png"));
    }
    if (name === "ea_inflation_horse_race") {
      assert(result.results[0].evaluation.origins[0].training_nobs === 40);
      assert(result.results[0].sensitivity.variants.length === 3);
      assert(
        (await page.evaluate(() => window.panelProgress)).some(
          (p) => p.phase === "forecast_evaluation",
        ),
      );
      await page.getByTestId("nav-builder").click();
      const n = await page.evaluate(() => window.panelRuns.length);
      await page.getByTestId("run-analysis").click();
      await page.getByTestId("cancel-analysis").click();
      await page.getByTestId("cancel-analysis").waitFor({ state: "hidden" });
      assert.equal(await page.evaluate(() => window.panelRuns.length), n);
      report.presentation.push(
        "Forecast progress and cancel verified; no cancelled result emitted",
      );
    }
  }
  assert.equal(report.external_requests.length, 0);
  await page
    .getByRole("button", { name: "MacroLab home", exact: true })
    .click();
  assert.equal(await page.locator('[data-testid^="template-"]').count(), 9);
  await checkView("home-nine-templates", "screen-home");
  for (const screen of ["library", "methods"]) {
    await page.getByTestId("nav-" + screen).click();
    await page.getByTestId("screen-" + screen).waitFor();
    const body = await page.locator("body").innerText();
    if (screen === "library") {
      assert(!body.includes("v2 · planned:"));
      if (process.env.MACROLAB_SCREENSHOT_GATE === "g16") {
        const links = await page
          .getByRole("link", { name: "Validation card", exact: true })
          .evaluateAll((nodes) => nodes.map((node) => node.href));
        assert.equal(links.length, 9);
        report.validation_cards = [];
        for (const url of new Set(links)) {
          assert(url.startsWith(origin + "/macrolab/validation/"));
          const response = await context.request.get(url);
          assert.equal(response.status(), 200);
          assert((await response.text()).includes("MacroLab"));
          report.validation_cards.push({
            url: new URL(url).pathname,
            status: response.status(),
          });
        }
        assert.equal(report.validation_cards.length, 6);
      }
    } else assert.match(body, /9 templates/);
    await checkView(screen + "-template-availability", "screen-" + screen);
  }
  assert.equal(report.external_requests.length, 0);
  assert.equal(report.failed_requests.length, 0);
  assert.equal(report.errors.length, 0);
  report.passed = true;
} finally {
  await writeFile(
    join(
      out,
      selectedCases
        ? "template-browser-validation-selected.json"
        : "template-browser-validation.json",
    ),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser?.close();
  await new Promise((r) => server.close(r));
}
