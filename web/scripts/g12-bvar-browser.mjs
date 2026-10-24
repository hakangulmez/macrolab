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
  out = resolve(root, process.env.MACROLAB_REVIEW_DIR ?? "runs/g12"),
  site = join(out, "site"),
  screens = join(
    root,
    "docs/screenshots",
    process.env.MACROLAB_SCREENSHOT_GATE ?? "g12",
  );
process.env.TMPDIR = join(root, ".cache/tmp");
await mkdir(join(out, "bvar-downloads"), { recursive: true });
await mkdir(screens, { recursive: true });
const ready = JSON.parse(await readFile(join(site, "data/manifest.json")));
const wheel = JSON.parse(await readFile(join(out, "runtime_wheel.json")));
assert.equal(
  ready.runtime.wheel_sha256,
  wheel.wheel_sha256,
  "Build must match current runtime source",
);
assert.equal(ready.schema_url, "schemas/analysis_config.schema.json");
const fixture = JSON.parse(await readFile(join(out, "bvar-fixture.json")));
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
      const axe = await new AxeBuilder({ page }).analyze();
      const violations = axe.violations.filter((v) =>
        ["serious", "critical"].includes(v.impact),
      );
      report.accessibility.push({ name, width, violations });
      assert.equal(violations.length, 0, JSON.stringify(violations));
      if (!process.env.MACROLAB_SKIP_SCREENSHOTS)
        await page
          .getByTestId(testId)
          .screenshot({ path: join(screens, `${name}-${width}.png`) });
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
  }
  for (const name of Object.keys(fixture.cases)) {
    await page.goto(
      origin + "/macrolab/?c=" + encodeURIComponent(fixture.tokens[name]),
    );
    await page.getByTestId("screen-builder").waitFor();
    await page.locator('main[data-runtime-status="ready"]').waitFor();
    if (name === "bvar_fixed") {
      assert.equal(
        await page
          .getByRole("combobox", { name: /^Posterior draws/ })
          .inputValue(),
        "1000",
      );
      assert.equal(
        await page
          .getByLabel("Sum-of-coefficients prior", { exact: true })
          .isChecked(),
        false,
      );
      assert.equal(
        await page
          .getByLabel("Co-persistence prior", { exact: true })
          .isChecked(),
        false,
      );
      await checkView("bvar-builder", "screen-builder");
    }
    const elapsed = [];
    let result;
    for (let i = 0; i < (name === "bvar_optional" ? 1 : 5); i++) {
      if (i) await page.getByTestId("nav-builder").click();
      const n = await page.evaluate(() => window.panelRuns.length),
        start = Date.now();
      await page.getByTestId("run-analysis").click();
      await page.waitForFunction((n) => window.panelRuns.length > n, n);
      result = await page.evaluate(() => window.panelRuns.at(-1));
      assert.equal(result.status, "ok", JSON.stringify(result.checks));
      await page.getByTestId("bvar-results").waitFor();
      await page
        .getByTestId("bvar-results")
        .locator("canvas")
        .first()
        .waitFor();
      await page.evaluate(
        () =>
          new Promise((r) =>
            requestAnimationFrame(() => requestAnimationFrame(r)),
          ),
      );
      elapsed.push(Date.now() - start);
    }
    const comparison = compare(
      JSON.parse(await readFile(join(out, name + ".json"))),
      result,
    );
    await writeFile(
      join(out, name + ".browser.json"),
      JSON.stringify(result) + "\n",
    );
    report.cases.push({ name, ...comparison, status: result.status });
    report.performance[name] = {
      runs_ms: elapsed,
      median_ms: quantile(elapsed, 0.5),
      p90_ms: quantile(elapsed, 0.9),
      target_ms: name === "bvar_fixed" ? 6000 : 3000,
    };
    for (const kind of ["csv", "png", "python"]) {
      const event = page.waitForEvent("download");
      await page.getByTestId("export-" + kind).click();
      await (
        await event
      ).saveAs(
        join(
          out,
          "bvar-downloads",
          name + "." + (kind === "python" ? "py" : kind),
        ),
      );
    }
    const view = page.getByTestId("bvar-results");
    assert.match(
      await view.innerText(),
      /own and cross-variable lags symmetrically/,
    );
    assert.equal(
      await view.locator(".chart-canvas").getAttribute("data-x-axis-title"),
      "Quarters after the shock",
    );
    await page
      .getByRole("combobox", { name: /^Posterior band/ })
      .selectOption("0.9");
    assert.match(await view.innerText(), /90% posterior credible band/);
    await page.getByLabel("BVAR response variable").selectOption("1");
    if (result.results[0].bvar.matched_ols.status === "ok") {
      await view.getByRole("button", { name: "OLS VAR", exact: true }).click();
      assert.equal(
        await view
          .getByRole("button", { name: "OLS VAR", exact: true })
          .getAttribute("aria-pressed"),
        "true",
      );
      assert.match(
        await view
          .getByRole("button", { name: "OLS VAR", exact: true })
          .getAttribute("class"),
        /primary/,
      );
      assert.match(await view.innerText(), /no OLS uncertainty band/);
      await view.getByRole("button", { name: "Both", exact: true }).click();
      assert.equal(
        await view
          .getByRole("button", { name: "Both", exact: true })
          .getAttribute("aria-pressed"),
        "true",
      );
      assert.equal(
        await view
          .getByRole("button", { name: "OLS VAR", exact: true })
          .getAttribute("aria-pressed"),
        "false",
      );
    }
    const event = page.waitForEvent("download");
    await view.getByRole("button", { name: /Export PNG:/ }).click();
    await (await event).saveAs(join(out, "bvar-downloads", name + "-90.png"));
    if (name !== "bvar_optional") await checkView(name, "bvar-results");
    console.log(
      name,
      JSON.stringify({ ...comparison, ...report.performance[name] }),
    );
  }
  assert(
    (await page.evaluate(() => window.panelProgress)).some(
      (p) => p.phase === "bvar_draws",
    ),
  );
  assert.equal(report.external_requests.length, 0);
  assert.equal(report.failed_requests.length, 0);
  assert.equal(report.errors.length, 0);
  report.passed = true;
} finally {
  await writeFile(
    join(out, "bvar-browser-validation.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser?.close();
  await new Promise((r) => server.close(r));
}
