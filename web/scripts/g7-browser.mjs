/* global window, document, Worker, requestAnimationFrame */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, extname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));
const out = join(root, "runs/g7"),
  site = join(out, "site");
process.env.TMPDIR = join(root, ".cache/tmp");
await mkdir(join(out, "downloads"), { recursive: true });
const report = {
  passed: false,
  cases: [],
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
        if (k === "runtime_ms") continue;
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
    window.g7Exports = [];
    const Original = Worker;
    window.Worker = class extends Original {
      constructor(...args) {
        super(...args);
        this.addEventListener("message", ({ data }) => {
          if (data.result?.results) window.g7Runs.push(data.result);
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
    await action();
    await page.waitForFunction((n) => window.g7Runs.length > n, n, {
      timeout: 180000,
    });
    await page.getByTestId("screen-results").waitFor();
    await page.getByTestId("v1-band-disclosure").waitFor();
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
    };
  }
  await page.goto(origin + "/macrolab/");
  for (const name of process.argv.includes("--tur-only")
    ? ["tur_pass_through"]
    : ["same_ecb_shock", "tur_pass_through"]) {
    if (name !== "same_ecb_shock")
      await page
        .getByRole("button", { name: "MacroLab home", exact: true })
        .click();
    await page.getByTestId("template-" + name).click();
    await page
      .locator('[data-testid="runtime-readiness"][data-runtime-status="ready"]')
      .waitFor();
    const run = await captureRun(() =>
      page.getByTestId("run-analysis").click(),
    );
    await writeFile(
      join(out, name + ".browser.json"),
      JSON.stringify(run.result) + "\n",
    );
    const expected = JSON.parse(await readFile(join(out, name + ".json")));
    const diff = compare(expected, run.result);
    report.cases.push({ name, ...diff, elapsed_ms: run.elapsed_ms });
    console.log(name, JSON.stringify(report.cases.at(-1)));
    for (const format of ["csv", "png", "python"]) {
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
      console.log("width check", name, width, JSON.stringify(overflow));
      assert(overflow.scroll <= width + 1, "Page overflow");
      await mkdir(join(root, "docs/screenshots/g7"), { recursive: true });
      await page.screenshot({
        path: join(root, "docs/screenshots/g7", name + "-" + width + ".png"),
        fullPage: true,
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
    if (name === "same_ecb_shock" && !process.argv.includes("--smoke")) {
      const times = [];
      for (
        let i = 0;
        i < (process.argv.includes("--measure-joint") ? 5 : 1);
        i++
      ) {
        const runJoint = await captureRun(async () => {
          if (i === 0) await page.getByTestId("compute-joint").click();
          else {
            await page
              .getByRole("button", {
                name: "← Edit this analysis",
                exact: true,
              })
              .click();
            await page.getByTestId("run-analysis").click();
          }
        });
        times.push(runJoint.elapsed_ms);
        const jointExpected = JSON.parse(
          await readFile(join(out, "same_ecb_shock-joint.json")),
        );
        report.joint_parity = compare(jointExpected, runJoint.result);
        await writeFile(
          join(out, "same_ecb_shock-joint.browser.json"),
          JSON.stringify(runJoint.result) + "\n",
        );
        console.log("joint click-to-render", i, runJoint.elapsed_ms);
      }
      const sorted = [...times].sort((a, b) => a - b);
      if (times.length === 5)
        report.timings.joint = {
          runs_ms: times,
          median_ms: sorted[2],
          p90_ms: sorted[4],
          includes_sensitivity: true,
        };
      // All warm runs include the full sensitivity set.
      const conditional = [];
      console.log("Starting conditional timings");
      for (let i = 0; i < 5; i++) {
        await page
          .getByRole("button", { name: "← Edit this analysis", exact: true })
          .click();
        await page.getByTestId("uncertainty-band").selectOption("conditional");
        const r = await captureRun(() =>
          page.getByTestId("run-analysis").click(),
        );
        conditional.push(r.elapsed_ms);
        console.log("conditional click-to-render", i, r.elapsed_ms);
      }
      const sortedC = [...conditional].sort((a, b) => a - b);
      report.timings.conditional = {
        runs_ms: conditional,
        median_ms: sortedC[2],
        p90_ms: sortedC[4],
        includes_sensitivity: true,
      };
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
      process.argv.includes("--tur-only")
        ? "tur-mobile-validation.json"
        : "browser-validation.json",
    ),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser?.close();
  await new Promise((r) => server.close(r));
}
