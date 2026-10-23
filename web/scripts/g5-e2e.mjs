/* global window, document */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const site = join(root, "runs/g5/site"),
  output = join(root, "runs/g5");
const screenshots = join(root, "docs/screenshots/g5");
await Promise.all(
  [
    output,
    screenshots,
    join(output, "downloads"),
    join(root, ".cache/tmp"),
  ].map((p) => mkdir(p, { recursive: true })),
);
process.env.TMPDIR = join(root, ".cache/tmp");
const report = {
  passed: false,
  templates: [],
  screens: [],
  exports: [],
  external_requests: [],
  failed_requests: [],
  page_errors: [],
  numerical_fields: 0,
  browser_maximum_absolute_difference: 0,
  native_maximum_absolute_difference: 0,
};
const excluded = new Set([
  "code_version",
  "runtime_ms",
  "source_data_sha256",
  "prepared_inputs_sha256",
  "snapshot_id",
  "config_hash",
]);
function compare(a, b, tolerance) {
  let count = 0,
    maximum = 0;
  function visit(x, y, path = "") {
    if (typeof x === "number" && typeof y === "number") {
      assert(Number.isFinite(x) && Number.isFinite(y));
      count++;
      maximum = Math.max(maximum, Math.abs(x - y));
      assert(Math.abs(x - y) <= tolerance, `${path}: ${x} versus ${y}`);
    } else if (Array.isArray(x)) {
      assert(Array.isArray(y));
      assert.equal(x.length, y.length, path);
      x.forEach((v, i) => visit(v, y[i], `${path}/${i}`));
    } else if (x && typeof x === "object") {
      const keys = Object.keys(x)
        .filter((k) => !excluded.has(k))
        .sort();
      assert.deepEqual(
        keys,
        Object.keys(y)
          .filter((k) => !excluded.has(k))
          .sort(),
        path,
      );
      keys.forEach((k) => visit(x[k], y[k], `${path}/${k}`));
    } else assert.equal(x, y, path);
  }
  visit(a, b);
  return { count, maximum };
}
const mime = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
};
const server = createServer(async (request, response) => {
  try {
    const pathname = new URL(request.url, "http://localhost").pathname;
    if (!pathname.startsWith("/macrolab/")) {
      response.writeHead(404).end();
      return;
    }
    const file = resolve(
      site,
      decodeURIComponent(pathname.slice("/macrolab/".length)) || "index.html",
    );
    if (!file.startsWith(site + "/")) {
      response.writeHead(403).end();
      return;
    }
    const bytes = await readFile(file);
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
const base = `http://127.0.0.1:${server.address().port}/macrolab/`;
let browser;
async function download(page, id, prefix) {
  const waiting = page.waitForEvent("download");
  await page.getByTestId(id).click();
  const file = await waiting;
  assert.equal(await file.failure(), null);
  const name = `${prefix}-${file.suggestedFilename()}`;
  await file.saveAs(join(output, "downloads", name));
  const bytes = await readFile(join(output, "downloads", name));
  assert(bytes.length > 100);
  if (id === "export-png") assert.equal(bytes.subarray(1, 4).toString(), "PNG");
  report.exports.push({ id, name, bytes: bytes.length });
}
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
  report.browser_version = browser.version();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
    serviceWorkers: "block",
  });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (["data:", "blob:"].includes(url.protocol)) return route.continue();
    if (!url.href.startsWith(base)) {
      report.external_requests.push(url.href);
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  await context.addInitScript(() => {
    window.__g5Results = [];
    window.__g5Ready = [];
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        const start = performance.now();
        this.addEventListener("message", (e) => {
          if (e.data?.text === "Analysis runtime ready")
            window.__g5Ready.push(performance.now() - start);
          if (
            e.data?.result?.config_hash &&
            Array.isArray(e.data.result.results)
          )
            window.__g5Results.push(e.data.result);
        });
      }
    };
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.on("pageerror", (e) => report.page_errors.push(String(e)));
  page.on("response", (r) => {
    if (r.status() >= 400)
      report.failed_requests.push({
        url: r.url().replace(new URL(base).origin, "<local>"),
        status: r.status(),
      });
  });
  const started = Date.now();
  await page.goto(base);
  await page.getByTestId("screen-home").waitFor();
  report.first_page_ms = Date.now() - started;
  assert.match(
    await page.getByTestId("screen-home").innerText(),
    /33 indicators \+ 3 (included )?global factors/i,
  );
  for (const id of [
    "monetary_policy",
    "taylor_rule",
    "phillips_curve",
    "okuns_law",
  ]) {
    console.log(`G5 browser: ${id}`);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByTestId("nav-home").click();
    await page.getByTestId(`template-${id}`).click();
    const n = await page.evaluate(() => window.__g5Results.length);
    await page.getByTestId("run-analysis").click();
    await page.waitForFunction((n) => window.__g5Results.length > n, n, {
      timeout: 120000,
    });
    await page.getByTestId("screen-results").waitFor();
    const result = await page.evaluate(() => window.__g5Results.at(-1));
    assert.equal(result.status, "ok");
    const original = JSON.parse(
      await readFile(join(root, `runs/p2/${id}.browser-result.json`), "utf8"),
    );
    const native = JSON.parse(
      await readFile(join(root, `runs/g5/native/${id}.json`), "utf8"),
    );
    const exact = compare(original, result, 0),
      parity = compare(native, result, 1e-8);
    report.numerical_fields += exact.count;
    report.browser_maximum_absolute_difference = Math.max(
      report.browser_maximum_absolute_difference,
      exact.maximum,
    );
    report.native_maximum_absolute_difference = Math.max(
      report.native_maximum_absolute_difference,
      parity.maximum,
    );
    report.templates.push({
      id,
      exact_fields: exact.count,
      browser_max_abs_diff: exact.maximum,
      native_max_abs_diff: parity.maximum,
      runtime_ms: result.runtime_ms,
      sample: result.actual_samples,
    });
    await writeFile(
      join(output, `${id}.browser-result.json`),
      JSON.stringify(result),
    );
    for (const control of ["export-png", "export-csv", "export-python"])
      await download(page, control, id);
    if (id === "monetary_policy") {
      await page.getByLabel("PNG scope", { exact: true }).selectOption("panel");
      await download(page, "export-png", `${id}-panel`);
      await page
        .getByLabel("PNG scope", { exact: true })
        .selectOption("selected");
    }
    for (const [name, width, height] of [
      ["desktop", 1440, 1000],
      ["mobile", 375, 812],
    ]) {
      await page.setViewportSize({ width, height });
      await page
        .getByTestId("result-chart")
        .first()
        .locator("canvas")
        .waitFor();
      await page.evaluate(() => document.fonts.ready);
      const audit = await new AxeBuilder({ page }).analyze();
      const serious = audit.violations.filter((v) =>
        ["serious", "critical"].includes(v.impact),
      );
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth,
      );
      assert.equal(serious.length, 0);
      assert.equal(overflow, false);
      const file = `${id}-${name}.png`;
      await page.screenshot({ path: join(screenshots, file), fullPage: true });
      report.screens.push({
        id,
        name,
        width,
        serious_or_critical: serious.length,
        horizontal_overflow: overflow,
        file: `docs/screenshots/g5/${file}`,
      });
      if (name === "mobile" && id === "monetary_policy") {
        await page
          .getByTestId("mobile-chart-selector")
          .selectOption({ index: 1 });
        await download(page, "export-png", `${id}-mobile-selected`);
      }
    }
  }
  await page.getByTestId("nav-catalogue").click();
  await page.getByLabel(/^Country/).selectOption("EA");
  await page.getByLabel("Search indicators", { exact: true }).fill("cpi");
  const priceCard = page
    .locator("article.card")
    .filter({ has: page.locator("code").filter({ hasText: /^cpi$/ }) });
  await priceCard
    .getByText("Sources, definitions & limitations", { exact: true })
    .click();
  assert.match(
    await priceCard.innerText(),
    /Official seasonally adjusted HICP/,
  );
  for (const [name, width, height] of [
    ["desktop", 1440, 1000],
    ["mobile", 375, 812],
  ]) {
    await page.setViewportSize({ width, height });
    const audit = await new AxeBuilder({ page }).analyze();
    const serious = audit.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact),
    );
    assert.equal(serious.length, 0);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    assert.equal(overflow, false);
    const file = `catalogue-variants-${name}.png`;
    await page.screenshot({ path: join(screenshots, file), fullPage: true });
    report.screens.push({
      id: "catalogue",
      name,
      width,
      serious_or_critical: 0,
      horizontal_overflow: overflow,
      file: `docs/screenshots/g5/${file}`,
    });
  }
  await page.getByTestId("nav-methods").click();
  assert.match(
    await page.getByTestId("screen-methods").innerText(),
    /non-commercial research and teaching tool/,
  );
  assert.match(
    await page.getByTestId("screen-methods").innerText(),
    /Primary Commodity Prices/,
  );
  report.runtime_preparation_ms = await page.evaluate(() => window.__g5Ready);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByTestId("nav-home").click();
  await page.getByTestId("template-monetary_policy").click();
  const warm = [];
  for (let i = 0; i < 5; i++) {
    const n = await page.evaluate(() => window.__g5Results.length),
      start = Date.now();
    await page.getByTestId("run-analysis").click();
    await page.waitForFunction((n) => window.__g5Results.length > n, n, {
      timeout: 120000,
    });
    const result = await page.evaluate(() => window.__g5Results.at(-1));
    assert.equal(result.status, "ok");
    warm.push({
      worker_ms: result.runtime_ms,
      click_to_result_ms: Date.now() - start,
      variants: result.results[0].sensitivity.variants.length,
    });
    if (i < 4)
      await page.getByRole("button", { name: /Edit this analysis/ }).click();
  }
  const quantile = (field, p) =>
    [...warm].map((r) => r[field]).sort((a, b) => a - b)[
      Math.ceil(p * warm.length) - 1
    ];
  report.monetary_performance = {
    runs: warm,
    median_ms: quantile("worker_ms", 0.5),
    p90_ms: quantile("worker_ms", 0.9),
    median_click_to_result_ms: quantile("click_to_result_ms", 0.5),
    p90_click_to_result_ms: quantile("click_to_result_ms", 0.9),
  };
  assert.equal(report.numerical_fields, 4042);
  assert.equal(report.external_requests.length, 0);
  assert.equal(report.failed_requests.length, 0);
  assert.equal(report.page_errors.length, 0);
  report.passed = true;
} catch (error) {
  report.error = String(error);
  throw error;
} finally {
  await writeFile(
    join(output, "browser-validation.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser?.close();
  await new Promise((r) => server.close(r));
}
