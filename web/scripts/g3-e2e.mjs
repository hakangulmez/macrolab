/* global window, document, getComputedStyle */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const target = process.env.G3_BASE_URL;
assert(
  target,
  "Set G3_BASE_URL to the already-running local application; this harness starts no server.",
);
const origin = new URL(target).origin;
assert(
  ["127.0.0.1", "localhost", "[::1]"].includes(new URL(origin).hostname),
  "G3 QA is local-only.",
);
process.env.TMPDIR = join(root, ".cache/tmp");
const gate = process.env.MACROLAB_REVIEW_GATE ?? "g4";
assert(["g3", "g31", "g4"].includes(gate), "Unsupported review gate");
const output = join(root, `runs/${gate}`);
const screenshotDirectory =
  gate === "g3"
    ? "docs/screenshots"
    : `docs/screenshots/${gate === "g31" ? "g3_1" : "g4"}`;
const screenshots = join(root, screenshotDirectory);
await Promise.all([
  mkdir(output, { recursive: true }),
  mkdir(screenshots, { recursive: true }),
  mkdir(join(output, "downloads"), { recursive: true }),
  mkdir(process.env.TMPDIR, { recursive: true }),
]);
const templateIds = [
  "monetary_policy",
  "taylor_rule",
  "phillips_curve",
  "okuns_law",
];
const screenIds = [
  "home",
  "builder",
  "library",
  "results",
  "catalogue",
  "methods",
];
const report = {
  schema_version: 1,
  gate,
  started_at: new Date().toISOString(),
  environment:
    "Installed Google Chrome; real local Pyodide Web Worker; no mocked data or computation",
  templates: [],
  screens: [],
  exports: [],
  flows: [],
  external_requests: [],
  failed_requests: [],
  page_errors: [],
  assertions: [],
};
const requests = new Set();
let browser;
const started = Date.now();
const timeout = setTimeout(() => {
  report.assertions.push("G3 QA exceeded its 15-minute overall deadline");
  void browser?.close();
}, 900000);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");

async function step(name, operation) {
  console.log(`G3 QA: ${name}`);
  const start = Date.now();
  try {
    const value = await operation();
    report.flows.push({ name, passed: true, elapsed_ms: Date.now() - start });
    return value;
  } catch (error) {
    report.flows.push({
      name,
      passed: false,
      elapsed_ms: Date.now() - start,
      error: String(error),
    });
    throw error;
  }
}

async function instrument(context) {
  await context.route("**/*", async (route) => {
    const url = route.request().url();
    const parsed = new URL(url);
    requests.add(url.replace(origin, "http://127.0.0.1:<local-port>"));
    if (
      parsed.origin !== origin &&
      !["data:", "blob:"].includes(parsed.protocol)
    ) {
      report.external_requests.push(url);
      await route.abort("blockedbyclient");
    } else {
      await route.continue();
    }
  });
  await context.addInitScript(() => {
    window.__g3Results = [];
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", (event) => {
          const result = event.data?.result;
          if (result?.config_hash && Array.isArray(result.results)) {
            window.__g3Results.push(result);
          }
        });
      }
    };
  });
}

async function screen(page, id) {
  await page.getByTestId(`nav-${id}`).click();
  await page.getByTestId(`screen-${id}`).waitFor({ state: "visible" });
}

async function captureResult(page, template) {
  const marker = page.getByTestId("result-status");
  await marker.waitFor({ state: "visible", timeout: 180000 });
  await page.waitForFunction(
    () =>
      document
        .querySelector('[data-testid="result-status"]')
        ?.textContent?.includes("Analysis complete"),
    undefined,
    { timeout: 180000 },
  );
  const actual = await page.evaluate(() => window.__g3Results.at(-1));
  assert(actual, "No completed real-worker result was observed");
  assert.equal(
    actual.status,
    "ok",
    `Template ${template} is not fully computable`,
  );
  assert.equal(
    await marker.getAttribute("data-config-hash"),
    actual.config_hash,
  );
  assert.equal(
    await marker.getAttribute("data-snapshot-id"),
    actual.snapshot_id,
  );
  assert.equal(await marker.getAttribute("data-result-status"), "ok");
  assert.equal(
    await marker.getAttribute("data-model-id"),
    actual.config.model.id,
  );
  assert(actual.results.every((result) => result.status === "ok"));
  assert(actual.results.every((result) => result.actual_sample.nobs > 0));
  const text = await page.getByTestId("screen-results").innerText();
  assert.match(
    text,
    /Association, not causation|Model-based scenario, not a forecast/i,
  );
  const charts = page.getByTestId("result-chart");
  assert(
    (await charts.count()) > 0,
    "Results need a chart backed by computed values",
  );
  for (let index = 0; index < (await charts.count()); index += 1) {
    const chart = charts.nth(index);
    await chart.locator("canvas, svg").first().waitFor({ state: "visible" });
    assert(
      (await chart.innerText()).trim().length > 20,
      "Chart text alternative is absent",
    );
    const tableToggle = chart.getByText("Show chart data", { exact: true });
    await tableToggle.click();
    const table = chart.getByRole("table");
    assert(
      await table.isVisible(),
      "Chart data table toggle did not reveal a table",
    );
    assert(
      (await table.getByRole("row").count()) > 1,
      "Chart data table has no observations",
    );
    assert.match(
      await table.innerText(),
      /\d/,
      "Chart data table has no numeric data",
    );
    assert.doesNotMatch(
      await table.innerText(),
      /\b(?:NaN|Infinity)\b/,
      "Chart data table contains non-finite values",
    );
    await tableToggle.click();
    assert(!(await table.isVisible()), "Chart data table did not close");
  }
  const evidence = {
    id: template,
    model_id: actual.config.model.id,
    config_hash: actual.config_hash,
    snapshot_id: actual.snapshot_id,
    result_status: actual.status,
    actual_samples: actual.actual_samples,
    chart_count: await charts.count(),
    runtime_ms: actual.runtime_ms,
    label: actual.label,
    worker_observed: true,
  };
  report.templates.push(evidence);
  return actual;
}

async function template(page, id) {
  await screen(page, "home");
  await page.getByTestId(`template-${id}`).click();
  await page.getByTestId("screen-builder").waitFor({ state: "visible" });
  const previous = await page.evaluate(() => window.__g3Results.length);
  await page.getByTestId("run-analysis").click();
  await page.waitForFunction(
    (count) => window.__g3Results.length > count,
    previous,
    { timeout: 180000 },
  );
  await page
    .getByTestId("screen-results")
    .waitFor({ state: "visible", timeout: 180000 });
  return captureResult(page, id);
}

async function download(page, id, extension) {
  const event = page.waitForEvent("download");
  await page.getByTestId(id).click();
  const file = await event;
  assert.equal(await file.failure(), null, `${id} download failed`);
  const filename = basename(file.suggestedFilename());
  assert(
    filename.toLowerCase().endsWith(extension),
    `${id} did not produce ${extension}`,
  );
  const path = join(output, "downloads", filename);
  await file.saveAs(path);
  const bytes = await readFile(path);
  assert(bytes.length > 60, `${id} export is empty or truncated`);
  report.exports.push({
    control: id,
    filename,
    bytes: bytes.length,
    sha256: hash(bytes),
  });
  return bytes;
}

async function tabTo(page, testId) {
  const target = page.getByTestId(testId);
  for (let attempt = 0; attempt < 260; attempt += 1) {
    await page.keyboard.press("Tab");
    if (
      await target.evaluate((element) => element === document.activeElement)
    ) {
      const visibleFocus = await target.evaluate((element) => {
        const style = getComputedStyle(element);
        return (
          (style.outlineStyle !== "none" &&
            parseFloat(style.outlineWidth) > 0) ||
          style.boxShadow !== "none"
        );
      });
      assert(
        visibleFocus,
        `${testId} lacks a visible keyboard focus indicator`,
      );
      return;
    }
  }
  throw new Error(`Keyboard could not reach ${testId}`);
}

async function auditScreens(page, viewportName, viewport) {
  await page.setViewportSize(viewport);
  for (const id of screenIds) {
    await screen(page, id);
    await page.evaluate(() => document.fonts.ready);
    const overflow = await page.evaluate(() => ({
      content: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
    }));
    const horizontalOverflow = overflow.content > overflow.viewport + 1;
    const audit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = audit.violations.filter((v) =>
      ["serious", "critical"].includes(v.impact),
    );
    const path = join(screenshots, `${id}-${viewportName}.png`);
    await page.screenshot({ path, fullPage: true, animations: "disabled" });
    report.screens.push({
      screen: id,
      viewport: viewportName,
      width: viewport.width,
      height: viewport.height,
      screenshot: `${screenshotDirectory}/${id}-${viewportName}.png`,
      page_height: await page.evaluate(
        () => document.documentElement.scrollHeight,
      ),
      screenshot_sha256: hash(await readFile(path)),
      axe_passes: audit.passes.length,
      violations: audit.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        description: v.description,
        nodes: v.nodes.map((node) => ({
          target: node.target,
          failure_summary: node.failureSummary,
        })),
      })),
      serious_or_critical: serious.length,
      horizontal_overflow: horizontalOverflow,
      content_width: overflow.content,
    });
    console.log(
      `G3 QA: ${id}/${viewportName} screenshot and axe ${audit.passes.length} passes`,
    );
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
  await instrument(context);
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  page.on("pageerror", (error) => report.page_errors.push(String(error)));
  page.on("response", (response) => {
    if (response.status() >= 400)
      report.failed_requests.push({
        url: response.url().replace(origin, "<local>"),
        status: response.status(),
      });
  });
  await step("Open local application", async () => {
    const response = await page.goto(origin);
    assert(response?.ok(), "Local app did not return HTTP success");
    await page
      .getByTestId("screen-home")
      .waitFor({ state: "visible", timeout: 120000 });
  });
  await step(
    "Explore links preserve country, indicator, category and euro area",
    async () => {
      await page.getByLabel("Search countries or indicators").fill("Germany");
      await page.getByRole("button", { name: /^Germany DEU/ }).click();
      assert.equal(await page.getByLabel(/^Country/).inputValue(), "DEU");
      await screen(page, "home");
      await page.getByLabel("Search countries or indicators").fill("gdp_real");
      await page.getByRole("button", { name: /gdp_real$/ }).click();
      assert.equal(
        await page
          .getByLabel("Search indicators", { exact: true })
          .inputValue(),
        "gdp_real",
      );
      await screen(page, "home");
      await page.getByRole("button", { name: /^Prices \d+$/ }).click();
      assert.equal(
        await page.getByLabel("Indicator category").inputValue(),
        "Prices",
      );
      await screen(page, "home");
      await page
        .getByRole("button", { name: "Euro area", exact: true })
        .click();
      assert.equal(await page.getByLabel(/^Country/).inputValue(), "EA");
      await screen(page, "home");
      await page
        .getByRole("button", { name: "Explore the data →", exact: true })
        .click();
      assert.equal(await page.getByLabel(/^Country/).inputValue(), "USA");
      assert.equal(
        await page
          .getByLabel("Search indicators", { exact: true })
          .inputValue(),
        "",
      );
    },
  );
  let defaultResult;
  for (const id of templateIds) {
    const result = await step(`Run real template ${id}`, () =>
      template(page, id),
    );
    if (id === "monetary_policy") defaultResult = result;
  }
  await step("Return to real monetary policy results", async () => {
    defaultResult = await template(page, "monetary_policy");
    if (gate === "g4")
      await writeFile(
        join(output, "monetary-result.json"),
        JSON.stringify(defaultResult, null, 2) + "\n",
      );
  });
  await step(
    "Computed warnings remain visible and comparison curves are selectable",
    async () => {
      const visibleChecks = page
        .getByRole("region", { name: "Analysis checks" })
        .first();
      assert(await visibleChecks.isVisible(), "Checks are absent");
      const important = page
        .getByRole("region", { name: "Important warnings" })
        .first();
      assert(
        await important.isVisible(),
        "Actual important cautions are hidden",
      );
      assert(
        (await important.locator(":scope > .warning-items > li").count()) <= 5,
      );
      const warningText = await visibleChecks.innerText();
      assert.doesNotMatch(
        warningText,
        /internal_gaps|unknown_adjustment|cross_country_adjustment_mismatch|carries source warnings/,
      );
      assert.match(warningText, /observations|sample/i);
      const notes = visibleChecks.locator(".warning-notes");
      assert.equal(
        await notes.getAttribute("open"),
        null,
        "Source notes should start collapsed",
      );
      await notes.locator(":scope > summary").click();
      const sources = defaultResult.results.flatMap((r) =>
        r.checks.filter((c) => c.code === "source_warning"),
      );
      const unique = new Set(
        sources.map((c) => `${c.country}:${c.concept_id}`),
      );
      assert.match(
        await notes.innerText(),
        new RegExp(`${unique.size} series (?:have|has) source notes`),
      );
      const sourceButton = notes.locator(".source-note-links button").first();
      await sourceButton.click();
      await page.getByTestId("screen-catalogue").waitFor({ state: "visible" });
      assert.equal(
        await page.getByLabel(/^Country/).inputValue(),
        sources[0].country,
      );
      assert.equal(
        await page
          .getByLabel("Search indicators", { exact: true })
          .inputValue(),
        sources[0].concept_id,
      );
      await screen(page, "results");
      const selector = page.getByLabel("Compare response curves with");
      const initial = await selector.inputValue();
      const values = await selector
        .locator("option")
        .evaluateAll((options) => options.map((option) => option.value));
      const alternative = values.find((value) => value !== initial);
      assert(alternative, "No second computed response variant is available");
      await selector.selectOption(alternative);
      assert.equal(await selector.inputValue(), alternative);
      assert(
        (await page.locator(".legend").innerText()).includes(
          await selector.locator("option:checked").textContent(),
        ),
      );
      const first = page.getByTestId("result-chart").first();
      await first.getByText("Show chart data", { exact: true }).click();
      const data = await first.getByRole("table").innerText();
      assert.match(data, /comparison/i);
      assert.doesNotMatch(data, /\b(?:NaN|Infinity)\b/);
      await first.getByText("Show chart data", { exact: true }).click();
      await selector.selectOption(initial);
    },
  );
  if (gate === "g4") {
    await step(
      "G4 severity and newly disclosed checks preserve their technical evidence",
      async () => {
        const checks = defaultResult.results[0].checks;
        const sample = checks.find((check) => check.code === "small_sample");
        const oil = checks.find(
          (check) =>
            check.code === "nonstationary_level" &&
            check.concept_id === "oil_brent",
        );
        assert.equal(sample.level, "info");
        assert(
          sample.observations_per_parameter >= 5 &&
            sample.observations_per_parameter < 10,
        );
        assert.equal(oil.level, "info");
        assert.equal(oil.role, "exogenous");
        assert.equal(typeof oil.adf_p_value, "number");
        assert(checks.every((check) => check.phase));
        const important = page.getByRole("region", {
          name: "Important warnings",
        });
        assert.equal(
          await important.locator(":scope > .warning-items > li").count(),
          5,
        );
        assert.equal(
          await important
            .getByText("Found after estimation", { exact: true })
            .count(),
          3,
        );
        assert.doesNotMatch(
          await important.innerText(),
          /non-stationary|observations per parameter/i,
        );
        const notes = page.locator(".warning-notes");
        assert.equal(await notes.getAttribute("open"), null);
        await notes.locator(":scope > summary").click();
        assert.match(
          await notes.innerText(),
          /Five to fewer than ten observations per parameter/,
        );
        assert.match(await notes.innerText(), /non-stationary/);
        await notes.locator(":scope > summary").click();
      },
    );
  }
  await step("CSV, PNG and Python exports", async () => {
    const csv = (await download(page, "export-csv", ".csv")).toString("utf8");
    assert(csv.trim().split(/\r?\n/).length >= 3, "CSV lacks data rows");
    assert.match(csv, /\d/, "CSV has no numeric results");
    const png = await download(page, "export-png", ".png");
    assert.equal(
      png.subarray(0, 8).toString("hex"),
      "89504e470d0a1a0a",
      "PNG signature differs",
    );
    assert(
      png.readUInt32BE(16) >= 200 && png.readUInt32BE(20) >= 100,
      "PNG is too small to contain chart",
    );
    const script = (await download(page, "export-python", ".py")).toString(
      "utf8",
    );
    assert.match(script, /macrolab/);
    assert(
      script.includes(defaultResult.snapshot_id),
      "Python export omitted data vintage",
    );
    assert(
      script.includes(defaultResult.config_hash),
      "Python export omitted configuration hash",
    );
  });
  await step(
    "Share URL roundtrip recomputes identical configuration",
    async () => {
      await page.getByTestId("share-link").click();
      const url = await page.getByTestId("share-url").inputValue();
      assert.equal(
        new URL(url).origin,
        origin,
        "Share URL unexpectedly leaves the local app",
      );
      assert(
        new URL(url).search || new URL(url).hash,
        "Share URL contains no configuration",
      );
      const expected = defaultResult.config_hash;
      await page.goto(url);
      await page
        .getByTestId("screen-builder")
        .waitFor({ state: "visible", timeout: 120000 });
      await page.getByTestId("run-analysis").click();
      await page.waitForFunction(
        () => window.__g3Results.length > 0,
        undefined,
        { timeout: 180000 },
      );
      const actual = await captureResult(page, "share_roundtrip");
      assert.equal(
        actual.config_hash,
        expected,
        "Shared configuration changed after decoding",
      );
    },
  );
  if (["g31", "g4"].includes(gate)) {
    await step(
      "G3.1 precise bootstrap control recomputes the real result",
      async () => {
        const precision = page.getByTestId("bootstrap-precision");
        for (const draws of [1000, 200]) {
          await precision.selectOption(String(draws));
          await page.waitForFunction(
            (expected) =>
              window.__g3Results.at(-1)?.config.outputs.irf.draws === expected,
            draws,
            { timeout: 180000 },
          );
          const computed = await captureResult(
            page,
            `monetary_policy_${draws}_draws`,
          );
          assert.equal(computed.config.outputs.irf.draws, draws);
        }
      },
    );
    await step(
      "G3.1 mobile summary, chart switching and sensitivity cards",
      async () => {
        await page.setViewportSize({ width: 375, height: 900 });
        await screen(page, "results");
        const summary = page.getByTestId("mobile-result-summary");
        assert(await summary.isVisible());
        assert.equal(await summary.locator("p").count(), 3);
        const charts = page.getByTestId("result-chart");
        assert.equal(
          await charts.count(),
          1,
          "Mobile must mount one chart at a time",
        );
        const selector = page.getByTestId("mobile-chart-selector");
        const options = await selector.locator("option").evaluateAll((items) =>
          items.map((item) => ({
            value: item.value,
            label: item.textContent,
          })),
        );
        assert.equal(
          options.length,
          defaultResult.results[0].irf.variables.length,
        );
        for (const item of options) {
          await selector.selectOption(item.value);
          assert.equal(await charts.count(), 1);
          assert((await charts.innerText()).includes(item.label));
        }
        await selector.selectOption(options[0].value);
        assert(await page.getByTestId("mobile-sensitivity-cards").isVisible());
        assert(
          (await page.getByTestId("reading-bullets").locator("li").count()) <=
            5,
        );
        const footnotes = await page
          .getByText(/selected-peak comparisons are descriptive/i)
          .count();
        assert.equal(footnotes, 1);
        await screen(page, "builder");
        assert.equal(await page.locator("article.compact-series").count(), 5);
        const advanced = page.locator("article.compact-series details").first();
        assert.equal(await advanced.getAttribute("open"), null);
        await advanced.locator(":scope > summary").click();
        assert(await advanced.getByLabel(/Aggregation/).isVisible());
        await advanced.locator(":scope > summary").click();
        const precision = page.getByLabel("Bootstrap precision");
        assert.equal(await precision.inputValue(), "200");
        await precision.selectOption("1000");
        assert.equal(await precision.inputValue(), "1000");
        await precision.selectOption("200");
        await screen(page, "results");
        await page.setViewportSize({ width: 1440, height: 1000 });
      },
    );
  }
  if (gate === "g4")
    await step(
      "Fresh default preserves first-run disclosure in screenshots",
      async () => {
        await template(page, "monetary_policy");
        assert.equal(
          await page
            .getByRole("region", { name: "Important warnings" })
            .getByText("Found after estimation", { exact: true })
            .count(),
          3,
        );
        // Reset editable Builder state while retaining the result's disclosure snapshot.
        await screen(page, "home");
        await page.getByTestId("template-monetary_policy").click();
        await page.getByTestId("screen-builder").waitFor({ state: "visible" });
        assert.match(
          await page
            .getByRole("region", { name: "Important warnings" })
            .innerText(),
          /Important · 2/,
        );
      },
    );
  await step("Desktop six-screen accessibility and screenshots", () =>
    auditScreens(page, "desktop", { width: 1440, height: 1000 }),
  );
  await step("375px six-screen accessibility and screenshots", () =>
    auditScreens(page, "mobile", { width: 375, height: 900 }),
  );
  await step("Keyboard home to template to run and export", async () => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(origin);
    await page.getByTestId("screen-home").waitFor({ state: "visible" });
    await tabTo(page, "template-monetary_policy");
    await page.keyboard.press("Enter");
    await page.getByTestId("screen-builder").waitFor({ state: "visible" });
    await tabTo(page, "run-analysis");
    await page.keyboard.press("Enter");
    await page
      .getByTestId("screen-results")
      .waitFor({ state: "visible", timeout: 180000 });
    await tabTo(page, "export-csv");
    const downloaded = page.waitForEvent("download");
    await page.keyboard.press("Enter");
    assert.equal(await (await downloaded).failure(), null);
  });
  await step("Cancellation and subsequent worker recovery", async () => {
    await screen(page, "builder");
    await page.getByTestId("run-analysis").click();
    await page.getByTestId("cancel-analysis").waitFor({ state: "visible" });
    await page.getByTestId("cancel-analysis").click();
    await page
      .getByText(/cancelled/i)
      .first()
      .waitFor({ state: "visible" });
    await page.getByTestId("run-analysis").click();
    await page
      .getByTestId("screen-results")
      .waitFor({ state: "visible", timeout: 180000 });
    await captureResult(page, "after_cancellation");
  });
  await step(
    "Editing during calculation cancels the stale request",
    async () => {
      await screen(page, "builder");
      const seed = page.getByLabel("Random seed");
      const changedSeed = Number(await seed.inputValue()) + 1;
      await page.getByTestId("run-analysis").click();
      await page.getByTestId("cancel-analysis").waitFor({ state: "visible" });
      await seed.fill(String(changedSeed));
      await page.getByTestId("cancel-analysis").waitFor({ state: "hidden" });
      assert(await page.getByTestId("screen-builder").isVisible());
      assert.equal(await seed.inputValue(), String(changedSeed));
      await page.getByTestId("run-analysis").click();
      await page
        .getByTestId("screen-results")
        .waitFor({ state: "visible", timeout: 180000 });
      const result = await captureResult(page, "after_inflight_edit");
      assert.equal(
        result.config.seed,
        changedSeed,
        "The stale request overwrote the edited configuration",
      );
    },
  );
  assert.equal(
    report.external_requests.length,
    0,
    "External requests were attempted",
  );
  assert.equal(
    report.failed_requests.length,
    0,
    "Local assets or requests failed",
  );
  assert.equal(
    report.page_errors.length,
    0,
    "Uncaught browser errors occurred",
  );
  assert.equal(report.screens.length, 12);
  const failedScreens = report.screens.filter(
    (view) => view.serious_or_critical > 0 || view.horizontal_overflow,
  );
  assert.equal(
    failedScreens.length,
    0,
    `Accessibility/overflow failed: ${failedScreens.map((view) => `${view.screen}/${view.viewport}`).join(", ")}`,
  );
  report.passed = true;
} catch (error) {
  report.passed = false;
  report.assertions.push(String(error));
  console.error(error);
  process.exitCode = 1;
} finally {
  clearTimeout(timeout);
  if (browser) await browser.close();
  report.elapsed_ms = Date.now() - started;
  report.requests = [...requests];
  report.finished_at = new Date().toISOString();
  await writeFile(
    join(output, "e2e.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log(
    `G3 QA report: runs/${gate}/e2e.json (${report.passed ? "PASS" : "FAIL"})`,
  );
}
