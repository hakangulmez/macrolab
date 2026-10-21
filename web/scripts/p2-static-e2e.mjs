/* global window, document, location */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const target = new URL(
  process.env.P2_BASE_URL ?? "http://127.0.0.1:5176/macrolab/",
);
assert(
  ["127.0.0.1", "localhost", "[::1]"].includes(target.hostname),
  "P2 review is local only",
);
assert.equal(
  target.pathname,
  "/macrolab/",
  "Exercise the Pages-style project prefix",
);
const output = join(root, "runs/p2");
const screenshotDirectory = "runs/p2/screenshots";
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
  gate: "P2",
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
  report.assertions.push("P2 review exceeded its nine-minute deadline");
  void browser?.close();
}, 540000);
async function step(name, action) {
  console.log(`P2 QA: ${name}`);
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
async function sourceCard(page, conceptId) {
  await page.getByLabel("Search indicators", { exact: true }).fill(conceptId);
  const card = page.locator("article.card").filter({
    has: page.locator("code").filter({ hasText: new RegExp(`^${conceptId}$`) }),
  });
  await card.waitFor({ state: "visible" });
  return card;
}
async function run(page, templateId, selectTemplate = true) {
  if (templateId && selectTemplate) {
    await screen(page, "home");
    await page.getByTestId(`template-${templateId}`).click();
  }
  await page.getByTestId("screen-builder").waitFor({ state: "visible" });
  const before = await page.evaluate(() => window.__p2Results.length);
  await page.getByTestId("run-analysis").click();
  await page.waitForFunction(
    (count) => window.__p2Results.length > count,
    before,
    { timeout: 180000 },
  );
  await page
    .getByTestId("screen-results")
    .waitFor({ state: "visible", timeout: 180000 });
  const result = await page.evaluate(() => window.__p2Results.at(-1));
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
async function saveDownload(page, control, templateId) {
  const event = page.waitForEvent("download");
  await page.getByTestId(control).click();
  const file = await event;
  assert.equal(await file.failure(), null);
  const name = `${templateId}-${basename(file.suggestedFilename())}`;
  const path = join(output, "downloads", name);
  await file.saveAs(path);
  const bytes = await readFile(path);
  assert(bytes.length > 60, `${control} produced an empty file`);
  report.exports.push({
    control,
    template_id: templateId,
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
    window.__p2Results = [];
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", (event) => {
          const result = event.data?.result;
          if (result?.config_hash && Array.isArray(result.results))
            window.__p2Results.push(result);
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
  assert.deepEqual(candidate.included_global_factors, [
    "oil_brent",
    "us_policy_rate",
  ]);
  assert(
    candidate.excluded_concepts.some(
      (item) => item.concept_id === "commod_idx",
    ),
  );
  assert.match(
    await page.getByTestId("screen-home").innerText(),
    /33 indicators \+ 2 included global factors/i,
  );
  assert.match(
    await page.getByTestId("excluded-concepts").innerText(),
    /Broad commodity index.*Not included/s,
  );

  for (const id of [
    "monetary_policy",
    "taylor_rule",
    "phillips_curve",
    "okuns_law",
  ]) {
    const original = JSON.parse(
      await readFile(join(root, `configs/templates/${id}.json`), "utf8"),
    );
    const successful = await step(
      `${id}: original default computes with charts and sensitivity`,
      async () => {
        const result = await run(page, id);
        assert.equal(
          result.status,
          "ok",
          `${id}: ${JSON.stringify(result.checks)}`,
        );
        assert.deepEqual(result.config.countries, original.countries);
        assert.deepEqual(
          result.config.series.map(({ concept_id, role, transform }) => ({
            concept_id,
            role,
            transform,
          })),
          original.series.map(({ concept_id, role, transform }) => ({
            concept_id,
            role,
            transform,
          })),
        );
        assert(result.results.every((item) => item.actual_sample.nobs > 0));
        assert(
          result.results.every((item) =>
            item.sensitivity.variants.some(
              (variant) =>
                variant.variant_id !== "baseline" &&
                variant.status === "available",
            ),
          ),
        );
        assert(
          result.results.every(
            (item) => item.actual_sample.frequency_conversion,
          ),
        );
        if (id === "monetary_policy") {
          assert.equal(result.config.outputs.irf.draws, 200);
          assert(
            result.config.series.some(
              (series) =>
                series.concept_id === "oil_brent" &&
                series.role === "exogenous",
            ),
          );
          assert(result.results[0].irf);
        } else {
          assert(
            result.results.every((item) => item.coefficients_table?.length > 0),
          );
        }
        await page
          .getByTestId("result-chart")
          .first()
          .locator("canvas")
          .waitFor({ state: "visible" });
        assert(
          await page
            .getByRole("heading", {
              name: "How much does the answer depend on the model?",
            })
            .isVisible(),
        );
        return result;
      },
    );
    await step(
      `${id}: PNG, CSV and Python exports preserve sample and configuration`,
      async () => {
        const png = await saveDownload(page, "export-png", id);
        assert.equal(png.subarray(1, 4).toString(), "PNG");
        for (const control of ["export-csv", "export-python"]) {
          const content = (await saveDownload(page, control, id)).toString(
            "utf8",
          );
          assert(content.includes(successful.snapshot_id));
          assert(content.includes(successful.config_hash));
          if (control === "export-csv")
            assert(
              content.split(/\r?\n/, 1)[0].includes('"variant_config_hash"'),
            );
        }
      },
    );
    await step(
      `${id}: static share link reproduces the actual estimate`,
      async () => {
        await page.getByTestId("share-link").click();
        const link = new URL(await page.getByTestId("share-url").inputValue());
        assert.equal(link.origin, target.origin);
        assert.equal(link.pathname, target.pathname);
        assert(link.searchParams.has("c"));
        await page.goto(link.href);
        const repeated = await run(page, `${id}_share`, false);
        assert.equal(repeated.status, "ok");
        assert.equal(repeated.config_hash, successful.config_hash);
        assert.deepEqual(repeated.actual_samples, successful.actual_samples);
        assert.deepEqual(
          repeated.results.map((item) => ({
            coefficients: item.coefficients_table,
            irf: item.irf,
            sensitivity: item.sensitivity,
          })),
          successful.results.map((item) => ({
            coefficients: item.coefficients_table,
            irf: item.irf,
            sensitivity: item.sensitivity,
          })),
        );
      },
    );
  }
  await step(
    "Source cards disclose EIA replacement, OECD and IMF attribution, and excluded commodity metadata",
    async () => {
      await screen(page, "catalogue");
      await page.getByLabel(/^Country/).selectOption("USA");
      const oil = await sourceCard(page, "oil_brent");
      await oil.locator("summary").click();
      let catalogue = await page.getByTestId("screen-catalogue").innerText();
      assert.match(catalogue, /Energy Information Administration|EIA/);
      assert.match(catalogue, /Notes · Withheld/);
      assert.doesNotMatch(catalogue, /Notes · DRAFT/);
      assert(
        (await page.locator('article.card a[href*="eia.gov"]').count()) > 0,
      );
      const gdp = await sourceCard(page, "gdp_real");
      await gdp.locator("summary").click();
      catalogue = await page.getByTestId("screen-catalogue").innerText();
      assert.match(catalogue, /OECD \(\d{4}\)/);
      assert(
        (await page.locator('article.card a[href*="oecd.org"]').count()) > 0,
      );
      const debt = await sourceCard(page, "gov_debt");
      await debt.locator("summary").click();
      catalogue = await page.getByTestId("screen-catalogue").innerText();
      assert.match(
        catalogue,
        /Source: International Monetary Fund, World Economic Outlook/,
      );
      assert((await debt.locator('a[href*="imf.org"]').count()) > 0);
      await sourceCard(page, "commod_idx");
      catalogue = await page.getByTestId("screen-catalogue").innerText();
      assert.match(catalogue, /not included|Not included|excluded/);
      const manifest = await page.evaluate(async () =>
        (await fetch(new URL("data/manifest.json", location.href))).json(),
      );
      const commodity = manifest.indicators.find(
        (indicator) => indicator.concept_id === "commod_idx",
      );
      assert.equal(commodity.publication.included, false);
      const data = await page.evaluate(async () =>
        (await fetch(new URL("data/countries/USA.json", location.href))).json(),
      );
      assert(!data.series.commod_idx || data.series.commod_idx.length === 0);
      assert(
        data.cards
          .filter((card) => card.concept_id === "oil_brent")
          .every((card) =>
            card.source_segments.every((segment) => segment.source === "EIA"),
          ),
      );
      const profiles = page.getByTestId("profile-source-details");
      await profiles.locator("summary").click();
      assert.match(await profiles.innerText(), /World Development Indicators/);
      assert(
        (await profiles
          .locator('a[href*="creativecommons.org/licenses/by/4.0"]')
          .count()) > 0,
      );
      await profiles.locator("summary").click();
      await screen(page, "methods");
      assert(
        await page
          .getByText(
            "MacroLab is a non-commercial research and teaching tool.",
            { exact: true },
          )
          .isVisible(),
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
    "All six screens at desktop and 375px: layout, charts and accessibility",
    async () => {
      await run(page, "monetary_policy");
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
    `P2 report: runs/p2/e2e.json (${report.passed ? "PASS" : "FAIL"})`,
  );
}
