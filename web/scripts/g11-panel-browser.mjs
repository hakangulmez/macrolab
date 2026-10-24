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
  out = resolve(root, process.env.MACROLAB_REVIEW_DIR ?? "runs/g11"),
  site = join(out, "site"),
  screens = join(
    root,
    "docs/screenshots",
    process.env.MACROLAB_SCREENSHOT_GATE ?? "g11",
  );
process.env.TMPDIR = join(root, ".cache/tmp");
await mkdir(join(out, "panel-downloads"), { recursive: true });
await mkdir(screens, { recursive: true });
const ready = JSON.parse(await readFile(join(site, "data/manifest.json")));
const wheel = JSON.parse(await readFile(join(out, "runtime_wheel.json")));
assert.equal(
  ready.runtime.wheel_sha256,
  wheel.wheel_sha256,
  "Build must match current runtime source",
);
assert.equal(ready.schema_url, "schemas/analysis_config.schema.json");
const fixture = JSON.parse(await readFile(join(out, "panel-fixture.json")));
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
        if (!["runtime_ms", "code_version"].includes(k))
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
    const Original = Worker;
    window.Worker = class extends Original {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", ({ data }) => {
          if (data.type === "result" && data.result?.results)
            window.panelRuns.push(data.result);
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
      const a = await new AxeBuilder({ page }).analyze();
      const violations = a.violations
        .filter((v) => ["serious", "critical"].includes(v.impact))
        .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }));
      report.accessibility.push({ name, width, violations });
      assert.equal(violations.length, 0, JSON.stringify(violations));
      if (name === "panel_fe_11") {
        const main = page.getByTestId(testId).locator("table").first();
        assert.equal(await main.locator("thead th").count(), 13);
        assert.match(
          await main.locator("caption").innerText(),
          /Pooled: Driscoll-Kraay; country OLS: HAC\(4\)/,
        );
        assert.equal(await main.locator(".coefficient-se").count(), 24);
        if (process.env.MACROLAB_PANEL_HAC_CARRYOVER) {
          const before = await main
            .locator(".coefficient-se")
            .allTextContents();
          await page
            .getByRole("combobox", { name: /^Country OLS covariance/ })
            .selectOption("conventional");
          assert.match(
            await main.locator("caption").innerText(),
            /country OLS: conventional/,
          );
          const after = await main.locator(".coefficient-se").allTextContents();
          assert.notDeepEqual(before, after);
          assert.equal(before[0], after[0]);
          await page
            .getByRole("combobox", { name: /^Country OLS covariance/ })
            .selectOption("HAC(4)");
        }
        const toggle = main.getByRole("button", {
          name: /COVID dummies \(6\)/,
        });
        assert.equal(await toggle.getAttribute("aria-expanded"), "false");
        await toggle.click();
        assert.match(await main.innerText(), /COVID dummy 2020 Q1/);
        assert.equal(await main.locator(".coefficient-se").count(), 96);
        await toggle.click();
        const cue = page
          .getByTestId(testId)
          .locator(".table-scroll-cue")
          .first();
        assert(await cue.isVisible());
        const wrap = page.getByTestId(testId).locator(".wide-country-table");
        const before = await main.locator("th").first().boundingBox();
        await wrap.evaluate((e) => (e.scrollLeft = e.scrollWidth));
        const after = await main.locator("th").first().boundingBox();
        assert(
          Math.abs(after.x - before.x) < 1,
          "First column must stay fixed",
        );
        const last = await main.locator("thead th").last().boundingBox();
        const bounds = await wrap.boundingBox();
        assert(
          last.x >= bounds.x &&
            last.x + last.width <= bounds.x + bounds.width + 1,
          "Last country reachable by scrolling",
        );
        await wrap.evaluate((e) => (e.scrollLeft = 0));
      }
      if (name.startsWith("panel_lp_") && testId === "panel-results") {
        const chart = page.getByTestId(testId).getByTestId("result-chart");
        assert.match(
          await chart.locator("figcaption").innerText(),
          /Pooled response of Real GDP.*Germany[\s\S]*cumulative % change/,
        );
        assert.equal(
          await chart
            .locator(".chart-canvas")
            .getAttribute("data-x-axis-title"),
          "Quarters after the shock",
        );
        if (process.env.MACROLAB_PANEL_HAC_CARRYOVER) {
          assert.match(
            await page.getByTestId(testId).innerText(),
            /Within R² \(horizon 0\)/,
          );
          assert.equal(
            (await chart.locator("figcaption").innerText()).match(
              /cumulative % change/g,
            ).length,
            1,
          );
        }
        const tables = page.getByTestId(testId).locator("details[open] table");
        for (const table of await tables.all()) {
          assert.deepEqual(await table.locator("thead th").allTextContents(), [
            "Horizon",
            "Estimate",
            "Std. error",
            "Lower",
            "Upper",
          ]);
          assert.match(
            await table.locator("caption").innerText(),
            /90% pointwise intervals/,
          );
          assert.deepEqual(
            await table.locator("tbody tr td:first-child").allTextContents(),
            Array.from({ length: 21 }, (_, i) => String(i)),
          );
        }
      }
      report.presentation.push({ name, width, passed: true });
      if (!process.env.MACROLAB_SKIP_SCREENSHOTS)
        await page
          .getByTestId(testId)
          .screenshot({ path: join(screens, `${name}-${width}.png`) });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  for (const [name, config] of Object.entries(fixture.cases)) {
    console.log("loading", name);
    await page.goto(
      origin + "/macrolab/?c=" + encodeURIComponent(fixture.tokens[name]),
    );
    await page.getByTestId("screen-builder").waitFor();
    await page.locator('main[data-runtime-status="ready"]').waitFor();
    console.log("ready", name);
    if (name === "panel_lp_4") {
      assert(
        await page
          .getByTestId("panel-controls")
          .locator("select[aria-describedby=panel-time-reason]")
          .locator('option[value="two_way"]')
          .evaluate((option) => option.disabled),
      );
      assert.match(
        await page.getByTestId("panel-controls").innerText(),
        /absorb the shock/,
      );
      await checkView("panel-lp-builder", "screen-builder");
    }
    const elapsed = [];
    let result;
    for (let i = 0; i < Number(process.env.MACROLAB_PANEL_RUNS ?? 5); i++) {
      if (i) {
        await page.getByTestId("nav-builder").click();
        await page.getByTestId("screen-builder").waitFor();
      }
      const n = await page.evaluate(() => window.panelRuns.length),
        start = Date.now();
      if (name === "panel_fe_11" && i === 0) {
        await page.getByTestId("run-analysis").focus();
        await page.keyboard.press("Enter");
      } else await page.getByTestId("run-analysis").click();
      await page.waitForFunction((n) => window.panelRuns.length > n, n);
      result = await page.evaluate(() => window.panelRuns.at(-1));
      assert.equal(
        result.status,
        "ok",
        JSON.stringify(result.checks.filter((c) => c.level === "block")),
      );
      await page.getByTestId("panel-results").waitFor();
      await page
        .locator('[data-testid="screen-results"] canvas')
        .first()
        .waitFor();
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() => requestAnimationFrame(r)),
          ),
      );
      elapsed.push(Date.now() - start);
      result = await page.evaluate(() => window.panelRuns.at(-1));
      assert.equal(
        result.status,
        "ok",
        JSON.stringify(result.checks.filter((c) => c.level === "block")),
      );
    }
    const expected = JSON.parse(await readFile(join(out, name + ".json"))),
      comparison = compare(expected, result);
    let acceptedComparison;
    if (process.env.MACROLAB_PANEL_ACCEPTED_DIR) {
      acceptedComparison = compare(
        JSON.parse(
          await readFile(
            join(
              root,
              process.env.MACROLAB_PANEL_ACCEPTED_DIR,
              name + ".browser.json",
            ),
          ),
        ),
        process.env.MACROLAB_PANEL_HAC_CARRYOVER && name === "panel_fe_11"
          ? (() => {
              const restored = structuredClone(result);
              const p = restored.results[0].panel;
              p.country_estimates = p.country_estimates_conventional;
              delete p.country_estimates_conventional;
              return restored;
            })()
          : result,
      );
      assert.equal(
        acceptedComparison.max,
        0,
        "Panel numerical results must remain exact",
      );
    }
    await writeFile(
      join(out, name + ".browser.json"),
      JSON.stringify(result) + "\n",
    );
    report.cases.push({
      name,
      ...comparison,
      accepted_comparison: acceptedComparison,
      status: result.status,
      countries: config.countries,
      N: result.results[0].panel.N,
      T_min: result.results[0].panel.T_min,
      T_max: result.results[0].panel.T_max,
    });
    report.performance[name] = {
      runs_ms: elapsed,
      median_ms: quantile(elapsed, 0.5),
      p90_ms: quantile(elapsed, 0.9),
      target_ms:
        name === "panel_fe_11" ? 1000 : name === "panel_lp_4" ? 3000 : 10000,
    };
    for (const kind of ["csv", "png", "python"]) {
      const event = page.waitForEvent("download");
      await page.getByTestId("export-" + kind).click();
      const d = await event;
      await d.saveAs(
        join(
          out,
          "panel-downloads",
          name + "." + (kind === "python" ? "py" : kind),
        ),
      );
    }
    if (name !== "panel_lp_17") await checkView(name, "panel-results");
    if (name === "panel_lp_4") {
      await page.getByLabel("Overlay country").selectOption("ESP");
      assert.match(
        await page.getByTestId("panel-results").innerText(),
        /Spain/,
      );
      const event = page.waitForEvent("download");
      await page
        .getByTestId("panel-results")
        .getByRole("button", { name: /Export PNG:/ })
        .click();
      await (
        await event
      ).saveAs(join(out, "panel-downloads", "panel_lp_4-overlay.png"));
    }
    console.log(
      name,
      JSON.stringify({ ...comparison, ...report.performance[name] }),
    );
  }
  await page.getByTestId("nav-builder").click();
  const n = await page.evaluate(() => window.panelRuns.length),
    np = await page.evaluate(() => window.panelProgress.length);
  await page.getByTestId("run-analysis").click();
  await page.waitForFunction(
    (np) =>
      window.panelProgress.slice(np).some((p) => p.phase === "panel_horizon"),
    np,
  );
  await page.getByTestId("cancel-analysis").click();
  await page.getByTestId("cancel-analysis").waitFor({ state: "hidden" });
  assert.equal(await page.evaluate(() => window.panelRuns.length), n);
  assert.match(await page.locator("body").innerText(), /Analysis cancelled/);
  report.cancellation = {
    passed: true,
    progress: await page.evaluate((np) => window.panelProgress.slice(np), np),
  };
  assert.equal(report.external_requests.length, 0);
  assert.equal(report.failed_requests.length, 0);
  assert.equal(report.errors.length, 0);
  report.passed = true;
} finally {
  await writeFile(
    join(out, "panel-browser-validation.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser?.close();
  await new Promise((r) => server.close(r));
}
