/* global window, document, location */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import { deflateSync } from "node:zlib";
import AxeBuilder from "@axe-core/playwright";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const target = new URL(
  process.env.P1_BASE_URL ?? "http://127.0.0.1:5175/macrolab/",
);
assert(
  ["127.0.0.1", "localhost", "[::1]"].includes(target.hostname),
  "P1 review is local only",
);
assert.equal(
  target.pathname,
  "/macrolab/",
  "Exercise the Pages-style project prefix",
);
const output = join(root, "runs/p1");
const screenshotDirectory = "docs/screenshots/p1";
const screenshots = join(root, screenshotDirectory);
process.env.TMPDIR = join(root, ".cache/tmp");
await Promise.all(
  [output, screenshots, join(output, "downloads"), process.env.TMPDIR].map(
    (path) => mkdir(path, { recursive: true }),
  ),
);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const report = {
  schema_version: 1,
  gate: "P1",
  started_at: new Date().toISOString(),
  base_path: target.pathname,
  environment:
    "Pure static server; installed Chrome under loopback-only sandbox; real Pyodide worker",
  flows: [],
  templates: [],
  exports: [],
  screens: [],
  requests: [],
  external_requests: [],
  api_requests: [],
  prefix_escapes: [],
  failed_requests: [],
  page_errors: [],
  assertions: [],
  passed: false,
};
let browser;
const started = Date.now();
const deadline = setTimeout(() => {
  report.assertions.push("P1 review exceeded its nine-minute deadline");
  void browser?.close();
}, 540000);
async function step(name, action) {
  console.log(`P1 QA: ${name}`);
  const before = Date.now();
  try {
    const result = await action();
    report.flows.push({ name, passed: true, elapsed_ms: Date.now() - before });
    return result;
  } catch (error) {
    report.flows.push({
      name,
      passed: false,
      elapsed_ms: Date.now() - before,
      error: String(error),
    });
    throw error;
  }
}
async function screen(page, id) {
  await page.getByTestId(`nav-${id}`).click();
  await page.getByTestId(`screen-${id}`).waitFor({ state: "visible" });
}
async function run(page, templateId, selectTemplate = true) {
  if (templateId && selectTemplate) {
    await screen(page, "home");
    await page.getByTestId(`template-${templateId}`).click();
  }
  await page.getByTestId("screen-builder").waitFor({ state: "visible" });
  const before = await page.evaluate(() => window.__p1Results.length);
  await page.getByTestId("run-analysis").click();
  await page.waitForFunction(
    (count) => window.__p1Results.length > count,
    before,
    { timeout: 180000 },
  );
  await page
    .getByTestId("screen-results")
    .waitFor({ state: "visible", timeout: 180000 });
  const result = await page.evaluate(() => window.__p1Results.at(-1));
  assert.equal(
    await page.getByTestId("result-status").getAttribute("data-config-hash"),
    result.config_hash,
  );
  report.templates.push({
    id: templateId ?? "share_roundtrip",
    status: result.status,
    config_hash: result.config_hash,
    snapshot_id: result.snapshot_id,
    actual_samples: result.actual_samples,
    runtime_ms: result.runtime_ms,
    checks: result.checks,
    browser_worker_observed: true,
  });
  await writeFile(
    join(output, `${templateId ?? "share_roundtrip"}.browser-result.json`),
    JSON.stringify(result, null, 2) + "\n",
  );
  return result;
}
async function saveDownload(page, control) {
  const event = page.waitForEvent("download");
  await page.getByTestId(control).click();
  const file = await event;
  assert.equal(await file.failure(), null);
  const name = basename(file.suggestedFilename());
  const path = join(output, "downloads", name);
  await file.saveAs(path);
  const bytes = await readFile(path);
  assert(bytes.length > 60, `${control} produced an empty file`);
  report.exports.push({
    control,
    filename: name,
    bytes: bytes.length,
    sha256: hash(bytes),
  });
  return bytes;
}
async function captureScreens(page) {
  for (const [viewport, width, height] of [
    ["desktop", 1440, 1000],
    ["mobile", 375, 812],
  ]) {
    await page.setViewportSize({ width, height });
    for (const id of [
      "home",
      "builder",
      "library",
      "results",
      "catalogue",
      "methods",
    ]) {
      await screen(page, id);
      await page.evaluate(() => document.fonts.ready);
      if (id === "results")
        await page
          .getByTestId("result-chart")
          .first()
          .locator("canvas")
          .waitFor({ state: "visible" });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      );
      const audit = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      const serious = audit.violations.filter((violation) =>
        ["serious", "critical"].includes(violation.impact),
      );
      const filename = `${id}-${viewport}.png`;
      const path = join(screenshots, filename);
      await page.screenshot({ path, fullPage: true, animations: "disabled" });
      report.screens.push({
        screen: id,
        viewport,
        width,
        height,
        screenshot: `${screenshotDirectory}/${filename}`,
        sha256: hash(await readFile(path)),
        page_height: await page.evaluate(
          () => document.documentElement.scrollHeight,
        ),
        serious_or_critical: serious.length,
        horizontal_overflow: overflow,
        violations: audit.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          description: v.description,
          nodes: v.nodes.map((n) => ({
            target: n.target,
            failure_summary: n.failureSummary,
          })),
        })),
      });
      assert.equal(
        serious.length,
        0,
        `${id}/${viewport}: serious accessibility violation`,
      );
      assert.equal(overflow, false, `${id}/${viewport}: horizontal overflow`);
    }
  }
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
    report.requests.push(url.href.replace(target.origin, "<local>"));
    if (url.origin !== target.origin) {
      report.external_requests.push(url.href);
      return route.abort("blockedbyclient");
    }
    if (/(^|\/)api(?:\/|$)/.test(url.pathname)) {
      report.api_requests.push(url.pathname);
      return route.abort("blockedbyclient");
    }
    if (!url.pathname.startsWith(target.pathname)) {
      report.prefix_escapes.push(url.pathname);
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  await context.addInitScript(() => {
    window.__p1Results = [];
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", (event) => {
          const result = event.data?.result;
          if (result?.config_hash && Array.isArray(result.results))
            window.__p1Results.push(result);
        });
      }
    };
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.on("pageerror", (error) => report.page_errors.push(String(error)));
  page.on("response", (response) => {
    if (response.status() >= 400)
      report.failed_requests.push({
        url: response.url().replace(target.origin, "<local>"),
        status: response.status(),
      });
  });
  await step(
    "Load static project subpath and visible publication scope",
    async () => {
      assert((await page.goto(target.href))?.ok());
      await page
        .getByTestId("screen-home")
        .waitFor({ state: "visible", timeout: 120000 });
      const notice = page.getByRole("complementary", {
        name: "Publication data scope",
      });
      assert(await notice.isVisible());
      assert.match(await notice.innerText(), /excluded|exclusions/);
      assert.match(await notice.innerText(), /Country notes are withheld/);
      assert(
        await page
          .locator('footer a[href="https://hakangulmez.github.io/"]')
          .isVisible(),
      );
      const manifest = await page.evaluate(async () =>
        (await fetch(new URL("data/manifest.json", location.href))).json(),
      );
      assert.equal(manifest.publication.mode, "static_candidate");
      assert.equal(manifest.publication.approved, false);
      assert.equal(manifest.publication.notes_withheld, true);
      report.publication = manifest.publication;
    },
  );
  const candidate = report.publication;
  assert(candidate);
  const customConfig = JSON.parse(
    await readFile(join(root, "configs/templates/okuns_law.json"), "utf8"),
  );
  customConfig.countries = ["USA"];
  customConfig.series = [
    { concept_id: "credit_pnfs", role: "dependent", transform: "diff" },
    { concept_id: "policy_rate", role: "regressor", transform: "diff" },
  ];
  customConfig.aggregation = { credit_pnfs: "mean", policy_rate: "mean" };
  customConfig.comparison = {
    enabled: true,
    methods: [],
    identifications: [],
    scenarios: [],
  };
  const customURL = new URL(target);
  customURL.searchParams.set(
    "c",
    "v1." + deflateSync(JSON.stringify(customConfig)).toString("base64url"),
  );
  report.custom_validation_configuration = {
    purpose:
      "BIS-only OLS smoke fixture; not a replacement default or causal interpretation",
    config: customConfig,
  };
  const successful = await step(
    "Custom BIS-only OLS model computes solely in the browser",
    async () => {
      await page.goto(customURL.href);
      const result = await run(page, "custom_bis_ols", false);
      assert.equal(result.status, "ok");
      assert(result.results.every((item) => item.actual_sample.nobs > 0));
      assert(
        result.results.every((item) => item.coefficients_table?.length > 0),
      );
      assert(
        result.results.every((item) =>
          item.sensitivity.variants.some(
            (variant) =>
              variant.variant_id !== "baseline" &&
              variant.status === "available",
          ),
        ),
      );
      await page
        .getByTestId("result-chart")
        .first()
        .locator("canvas")
        .waitFor({ state: "visible" });
      return result;
    },
  );
  await step(
    "Browser exports preserve the candidate sample and configuration",
    async () => {
      const png = await saveDownload(page, "export-png");
      assert.equal(png.subarray(1, 4).toString(), "PNG");
      const csv = (await saveDownload(page, "export-csv")).toString("utf8");
      assert(csv.includes(successful.snapshot_id));
      assert(csv.includes(successful.config_hash));
      const script = (await saveDownload(page, "export-python")).toString(
        "utf8",
      );
      assert(script.includes(successful.snapshot_id));
      assert(script.includes(successful.config_hash));
    },
  );
  await step(
    "Share link remains under the prefix and reproduces the estimate",
    async () => {
      await page.getByTestId("share-link").click();
      const link = new URL(await page.getByTestId("share-url").inputValue());
      assert.equal(link.origin, target.origin);
      assert.equal(link.pathname, target.pathname);
      assert(link.searchParams.has("c"));
      await page.goto(link.href);
      const repeated = await run(page);
      assert.equal(repeated.status, "ok");
      assert.equal(repeated.config_hash, successful.config_hash);
      assert.deepEqual(repeated.actual_samples, successful.actual_samples);
      assert.deepEqual(
        repeated.results[0].coefficients_table,
        successful.results[0].coefficients_table,
      );
    },
  );
  await step(
    "Excluded Brent blocks the unchanged USA monetary template visibly",
    async () => {
      const result = await run(page, "monetary_policy");
      assert.notEqual(result.status, "ok");
      assert.equal(result.config.countries[0], "USA");
      assert(
        result.config.series.some(
          (series) =>
            series.concept_id === "oil_brent" && series.role === "exogenous",
        ),
      );
      assert(
        result.checks.some(
          (check) =>
            check.level === "block" && check.concept_id === "oil_brent",
        ),
      );
      assert(
        await page
          .getByRole("region", { name: "Blocking checks", exact: true })
          .isVisible(),
      );
      assert(await page.getByTestId("export-python").isDisabled());
    },
  );
  await step(
    "Remaining unchanged defaults disclose their actual data availability",
    async () => {
      for (const id of ["taylor_rule", "phillips_curve", "okuns_law"]) {
        const original = JSON.parse(
          await readFile(join(root, `configs/templates/${id}.json`), "utf8"),
        );
        const result = await run(page, id);
        assert.deepEqual(result.config.countries, original.countries);
        if (result.status !== "ok") {
          assert(result.checks.some((check) => check.level === "block"));
          assert(
            await page
              .getByRole("region", { name: "Blocking checks", exact: true })
              .isVisible(),
          );
        }
      }
    },
  );
  await step(
    "Affected card explains exclusions and country drafts stay withheld",
    async () => {
      await screen(page, "catalogue");
      await page.getByLabel(/^Country/).selectOption("USA");
      await page
        .getByLabel("Search indicators", { exact: true })
        .fill("oil_brent");
      await page
        .getByTestId("source-exclusion-note")
        .first()
        .waitFor({ state: "visible" });
      const catalogue = await page.getByTestId("screen-catalogue").innerText();
      assert.match(catalogue, /Source data excluded from this candidate/);
      assert.match(catalogue, /WorldBank — not included/);
      assert.doesNotMatch(catalogue, /No mapped source/);
      assert.doesNotMatch(catalogue, /no verified mapping or observations/);
      assert.match(catalogue, /0 retained/);
      assert.match(catalogue, /Notes · Withheld/);
      assert.doesNotMatch(catalogue, /Notes · DRAFT/);
      const profileSources = page.getByTestId("profile-source-details");
      await profileSources.locator("summary").click();
      assert.match(
        await profileSources.innerText(),
        /World Development Indicators/,
      );
      assert.match(await profileSources.innerText(), /UN Population Division/);
      assert(
        (await profileSources
          .locator('a[href*="creativecommons.org/licenses/by/4.0"]')
          .count()) > 0,
      );
      await profileSources.locator("summary").click();
      await screen(page, "methods");
      assert(
        await page.getByRole("heading", { name: "About MacroLab" }).isVisible(),
      );
      assert(await page.getByTestId("publication-source-policy").isVisible());
      assert(
        await page
          .locator('a[href="https://hakangulmez.github.io/"]')
          .first()
          .isVisible(),
      );
    },
  );
  await step(
    "Desktop and 375px static-candidate screenshots and accessibility",
    async () => {
      await page.goto(customURL.href);
      await run(page, "custom_bis_ols", false);
      await captureScreens(page);
    },
  );
  assert.deepEqual(report.external_requests, []);
  assert.deepEqual(report.api_requests, []);
  assert.deepEqual(report.prefix_escapes, []);
  assert.deepEqual(report.failed_requests, []);
  assert.deepEqual(report.page_errors, []);
  report.passed = true;
} catch (error) {
  report.assertions.push(String(error));
  console.error(error);
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  if (browser) await browser.close();
  report.elapsed_ms = Date.now() - started;
  report.finished_at = new Date().toISOString();
  report.requests = [...new Set(report.requests)];
  await writeFile(
    join(output, "e2e.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log(
    `P1 report: runs/p1/e2e.json (${report.passed ? "PASS" : "FAIL"})`,
  );
}
