/* global window, document, Worker, requestAnimationFrame */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, extname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const out = join(root, "runs/g8"),
  site = join(out, "site");
process.env.TMPDIR = join(root, ".cache/tmp");
await mkdir(join(out, "downloads"), { recursive: true });
const report = {
  passed: false,
  cases: [],
  methods: [],
  timings: JSON.parse(
    await readFile(join(out, "performance.json"), "utf8").catch(() => "{}"),
  ),
  external_requests: [],
  failed_requests: [],
  errors: [],
  accessibility: [],
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
    const bytes = await readFile(file);
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
      .end(bytes);
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const origin = `http://127.0.0.1:${server.address().port}`;
function compare(a, b) {
  let max = 0,
    count = 0;
  function visit(x, y, path = "") {
    if (typeof x === "number") {
      assert.equal(typeof y, "number", path);
      const diff = Math.abs(x - y);
      assert(diff <= 1e-8, `${path}: ${x} vs ${y}`);
      max = Math.max(max, diff);
      count++;
    } else if (Array.isArray(x)) {
      assert.equal(x.length, y.length, path);
      x.forEach((v, i) => visit(v, y[i], path + "/" + i));
    } else if (x && typeof x === "object") {
      for (const k of Object.keys(x)) {
        if (["runtime_ms", "shock_fingerprint"].includes(k)) continue;
        visit(x[k], y[k], path + "/" + k);
      }
    } else assert.equal(x, y, path);
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
    if (new URL(route.request().url()).origin !== origin) {
      report.external_requests.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  page.on("pageerror", (e) => report.errors.push(String(e)));
  page.on("response", (r) => {
    if (r.status() >= 400) report.failed_requests.push(r.url());
  });
  await page.addInitScript(() => {
    window.g7Runs = [];
    window.g8Pairs = [];
    window.g71Partial = [];
    window.g7Exports = [];
    const Original = Worker;
    window.Worker = class extends Original {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", ({ data }) => {
          if (
            data.type === "result" &&
            data.result?.include_in_baseline_agreement_counts === false
          )
            window.g8Pairs.push(data.result);
          if (data.type === "partial") window.g71Partial.push(data.result);
          if (data.type === "result" && data.result?.results)
            window.g7Runs.push(data.result);
          if (
            typeof data.result === "string" &&
            data.result.includes("METADATA")
          )
            window.g7Exports.push(data.result);
        });
      }
    };
  });
  async function captureRun(action) {
    const n = await page.evaluate(() => window.g7Runs.length);
    const started = Date.now();
    const np = await page.evaluate(() => window.g71Partial.length);
    await action();
    let baseline_ms;
    if (await page.getByTestId("screen-builder").count()) {
      // Whichever arrives first: an ECB baseline event or a completed non-streamed result.
      await page.waitForFunction(
        ({ n, np }) =>
          window.g71Partial.length > np || window.g7Runs.length > n,
        { n, np },
        { timeout: 180000 },
      );
      await page.getByTestId("screen-results").waitFor();
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
      baseline_ms = Date.now() - started;
      if (await page.evaluate((np) => window.g71Partial.length > np, np)) {
        assert.match(
          await page.getByTestId("sensitivity-progress").innerText(),
          /computing in the background/,
        );
        assert(await page.getByTestId("export-csv").isDisabled());
        assert(await page.getByTestId("export-png").isDisabled());
        assert.equal(await page.evaluate(() => window.g7Runs.length), n);
      }
    }
    await page.waitForFunction((n) => window.g7Runs.length > n, n, {
      timeout: 180000,
    });
    await page.getByTestId("screen-results").waitFor();

    await page.waitForFunction(
      () =>
        document.querySelector('[data-testid="screen-results"] canvas') !==
        null,
    );
    await page.evaluate(
      () =>
        new Promise((r) =>
          requestAnimationFrame(() => requestAnimationFrame(r)),
        ),
    );
    return {
      result: await page.evaluate(() => window.g7Runs.at(-1)),
      elapsed_ms: Date.now() - started,
      baseline_ms,
      partial_rows: await page.evaluate(
        (np) =>
          window.g71Partial.slice(np).map((x) => x.template_sensitivity.length),
        np,
      ),
    };
  }
  await page.goto(origin + "/macrolab/");
  const single = process.argv
    .find((a) => a.startsWith("--template="))
    ?.split("=")[1];
  const names = single
    ? [single]
    : [
        "monetary_policy",
        "taylor_rule",
        "phillips_curve",
        "okuns_law",
        "same_ecb_shock",
        "tur_pass_through",
      ];
  for (const name of names) {
    await page
      .getByRole("button", { name: "MacroLab home", exact: true })
      .click();
    const preparationStarted = Date.now();
    await page.getByTestId("template-" + name).click();
    await page
      .locator('[data-testid="runtime-readiness"][data-runtime-status="ready"]')
      .waitFor();
    const preparation_ms = Date.now() - preparationStarted;
    const run = await captureRun(() =>
      page.getByTestId("run-analysis").click(),
    );
    await writeFile(
      join(out, name + ".browser.json"),
      JSON.stringify(run.result) + "\n",
    );
    const expected = JSON.parse(await readFile(join(out, name + ".json")));
    const diff = compare(expected, run.result);
    if (name === "same_ecb_shock")
      assert.deepEqual(run.partial_rows, [0, 1, 2, 3, 4, 5, 6, 7, 8]);
    report.cases.push({
      name,
      ...diff,
      preparation_ms,
      elapsed_ms: run.elapsed_ms,
      baseline_ms: run.baseline_ms,
    });
    console.log(name, JSON.stringify(report.cases.at(-1)));
    if (
      ["monetary_policy", "tur_pass_through", "same_ecb_shock"].includes(name)
    )
      await page.getByLabel("PNG scope", { exact: true }).selectOption("panel");
    for (const format of process.argv.includes("--skip-exports")
      ? []
      : process.argv.includes("--png-only")
        ? ["png"]
        : ["csv", "png", "python"]) {
      const downloadPromise = page.waitForEvent("download");
      await page.getByTestId("export-" + format).click();
      const download = await downloadPromise;
      await download.saveAs(
        join(
          out,
          "downloads",
          name + "." + (format === "python" ? "py" : format),
        ),
      );
      if (format === "png") {
        await mkdir(join(root, "docs/screenshots/g8/exports"), {
          recursive: true,
        });
        await download.saveAs(
          join(root, "docs/screenshots/g8/exports", name + ".png"),
        );
      }
      console.log("downloaded", name, format);
    }
    for (const width of [1440, 375]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.mouse.move(0, 0);
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() => requestAnimationFrame(r)),
          ),
      );
      const overflow = await page.evaluate(() => ({
        width: window.innerWidth,
        scroll: document.documentElement.scrollWidth,
        elements: [...document.querySelectorAll("body *")]
          .filter(
            (e) => e.getBoundingClientRect().right > window.innerWidth + 1,
          )
          .slice(0, 15)
          .map((e) => ({
            tag: e.tagName,
            cls: e.className,
            right: e.getBoundingClientRect().right,
            html: e.outerHTML.slice(0, 200),
          })),
      }));
      console.log("width check", name, width, overflow.scroll);
      assert(overflow.scroll <= width + 1, "Page overflow");
      await mkdir(join(root, "docs/screenshots/g8"), { recursive: true });
      await page.screenshot({
        path: join(root, "docs/screenshots/g8", name + "-" + width + ".png"),
        fullPage: true,
      });
      if (name === "same_ecb_shock")
        await page.getByTestId("country-comparison").screenshot({
          path: join(
            root,
            "docs/screenshots/g8",
            "country-comparison-" + width + ".png",
          ),
        });
      const a = await new AxeBuilder({ page }).analyze();
      report.accessibility.push({
        name,
        width,
        violations: a.violations
          .filter((v) => ["serious", "critical"].includes(v.impact))
          .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
      });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    if (["monetary_policy", "tur_pass_through"].includes(name)) {
      const panel = page.getByTestId("method-comparison");
      const selected = name === "monetary_policy" ? "gdp_real" : "cpi";
      await panel
        .getByLabel("Method comparison response", { exact: true })
        .selectOption(selected);
      const n = await page.evaluate(() => window.g8Pairs.length);
      const started = Date.now();
      await panel
        .getByRole("button", { name: "Compute matched VAR / LP", exact: true })
        .click();
      await page.waitForFunction((n) => window.g8Pairs.length > n, n);
      await panel.getByRole("button", { name: "both", exact: true }).waitFor();
      const pair = await page.evaluate(() => window.g8Pairs.at(-1));
      await writeFile(
        join(out, name + "-methods.browser.json"),
        JSON.stringify(pair) + "\n",
      );
      assert.equal(pair.status, "ok", JSON.stringify(pair));
      const expected = JSON.parse(
        await readFile(join(out, name + "-methods.json")),
      );
      report.methods.push({
        name,
        ...compare(expected, pair),
        elapsed_ms: Date.now() - started,
      });
      for (const mode of ["VAR", "LP", "both"]) {
        await panel.getByRole("button", { name: mode, exact: true }).click();
        assert.equal(
          await panel
            .getByRole("button", { name: mode, exact: true })
            .getAttribute("aria-pressed"),
          "true",
        );
      }
      for (const format of process.argv.includes("--skip-exports") ||
      process.argv.includes("--png-only")
        ? []
        : ["JSON", "CSV", "Python", "PNG"]) {
        const event = page.waitForEvent("download");
        await panel
          .getByRole("button", { name: "Comparison " + format, exact: true })
          .click();
        const d = await event;
        await d.saveAs(
          join(
            out,
            "downloads",
            name +
              "-methods." +
              (format === "Python" ? "py" : format.toLowerCase()),
          ),
        );
      }
      for (const width of [1440, 375]) {
        await page.setViewportSize({ width, height: 1000 });
        await panel.scrollIntoViewIfNeeded();
        await panel.screenshot({
          path: join(
            root,
            "docs/screenshots/g8",
            name + "-methods-" + width + ".png",
          ),
        });
        const a = await new AxeBuilder({ page }).analyze();
        report.accessibility.push({
          name: name + "-methods",
          width,
          violations: a.violations
            .filter((v) => ["serious", "critical"].includes(v.impact))
            .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
        });
      }
    }
    if (name === "same_ecb_shock") {
      await page.setViewportSize({ width: 375, height: 1000 });
      await page.getByTestId("comparison-country").selectOption("ESP");
      assert.equal(
        await page
          .getByTestId("country-comparison")
          .getByTestId("result-chart")
          .count(),
        2,
      );
      assert.match(
        await page.getByTestId("country-comparison").innerText(),
        /Spain/,
      );
      await page
        .getByLabel("Compare response", { exact: true })
        .selectOption("cpi");
      assert.match(
        await page.getByTestId("country-comparison").innerText(),
        /HICP/,
      );
      await page.getByTestId("comparison-country").selectOption("DEU");
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  if (!single) {
    for (const screen of [
      "home",
      "builder",
      "library",
      "catalogue",
      "methods",
    ]) {
      await page.getByTestId("nav-" + screen).click();
      await page.getByTestId("screen-" + screen).waitFor();
      for (const width of [1440, 375]) {
        await page.setViewportSize({ width, height: 1000 });
        const a = await new AxeBuilder({ page }).analyze();
        report.accessibility.push({
          name: screen,
          width,
          violations: a.violations
            .filter((v) => ["serious", "critical"].includes(v.impact))
            .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
        });
        if (["builder", "library", "methods"].includes(screen))
          await page.screenshot({
            path: join(
              root,
              "docs/screenshots/g8",
              screen + "-" + width + ".png",
            ),
            fullPage: true,
          });
        assert(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth + 1,
          ),
          screen + " overflow",
        );
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
  }

  assert.equal(report.external_requests.length, 0);
  assert.equal(report.failed_requests.length, 0);
  assert.equal(report.errors.length, 0);
  assert(report.accessibility.every((r) => r.violations.length === 0));
  report.passed = true;
} finally {
  await writeFile(
    join(
      out,
      process.argv.some((a) => a.startsWith("--template="))
        ? `browser-${process.argv.find((a) => a.startsWith("--template="))?.split("=")[1]}-validation.json`
        : "browser-validation.json",
    ),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser?.close();
  await new Promise((r) => server.close(r));
}
