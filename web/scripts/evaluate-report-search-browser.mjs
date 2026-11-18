/* global window, document, requestAnimationFrame */
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  loadEvidencePool,
  gradeEvidence,
  summarizeEvidence,
} from "./report-search-evaluation.mjs";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const [base, goldPath, outputPath] = process.argv.slice(2);
if (!base || !goldPath || !outputPath)
  throw new Error(
    "Usage: node scripts/evaluate-report-search-browser.mjs LOOPBACK_URL GOLD.json NEW_OUTPUT_DIR",
  );
const target = new URL(base);
assert(["127.0.0.1", "localhost", "[::1]"].includes(target.hostname));
await mkdir(outputPath, { recursive: false });
const gold = JSON.parse(await readFile(goldPath));
const { pool } = await loadEvidencePool(webRoot);
const originals = new Map(pool.map((p) => [p.id, p]));
const report = {
  environment:
    "Production build, normal headless Chrome, loopback static server",
  latencyDefinition:
    "Form submit event to visible answer DOM plus two animation frames. Cold contexts include worker start, shard fetch, integrity check, decompression and indexing. Page navigation excluded. Not a public-network latency claim.",
  cold: [],
  warm: [],
  views: [],
  errors: [],
  requests: [],
  workers: [],
};
const browser = await chromium.launch({ channel: "chrome", headless: true });
report.browserVersion = browser.version();
const save = () =>
  writeFile(
    resolve(outputPath, "browser.json"),
    JSON.stringify(report, null, 2),
  );
async function open(width = 1440, theme = "dark") {
  const context = await browser.newContext({
    viewport: { width, height: 1000 },
    colorScheme: theme,
    serviceWorkers: "block",
  });
  await context.addInitScript((value) => {
    localStorage.setItem("macrolab-theme", value);
    window.__evidence = null;
    window.__submitted = 0;
    document.addEventListener(
      "submit",
      () => {
        window.__evidence = null;
        window.__submitted = performance.now();
      },
      true,
    );
    window.addEventListener("macrolab-evidence-ready", (event) => {
      window.__evidence = event.detail.answer;
    });
  }, theme);
  const page = await context.newPage();
  page.on("pageerror", (e) => report.errors.push(String(e)));
  page.on("requestfailed", (r) =>
    report.errors.push(`${r.url()}: ${r.failure()?.errorText}`),
  );
  page.on("request", (r) => {
    const url = new URL(r.url());
    if (!report.requests.includes(url.origin + url.pathname))
      report.requests.push(url.origin + url.pathname);
  });
  page.on("worker", (w) => {
    if (!report.workers.includes(w.url())) report.workers.push(w.url());
  });
  await page.goto(`${base}#reports`);
  await page
    .getByRole("textbox", { name: "Your question", exact: true })
    .waitFor();
  // Finish ordinary page/font loading before measuring a query, and before
  // closing a short-lived context. Report-index loading still starts on submit.
  await page.evaluate(() => document.fonts.ready);
  await page.waitForLoadState("networkidle");
  return { context, page };
}
async function ask(page, q) {
  assert.deepEqual(
    q.filters,
    {},
    "Extend browser filter setup for nonempty gold filters",
  );
  await page
    .getByRole("textbox", { name: "Your question", exact: true })
    .fill(q.question);
  await page
    .getByRole("button", { name: "Find evidence", exact: true })
    .click();
  await page.getByTestId("evidence-answer").waitFor({ timeout: 30000 });
  const data = await page.evaluate(async () => {
    await new Promise((done) =>
      requestAnimationFrame(() => requestAnimationFrame(done)),
    );
    return {
      answer: window.__evidence,
      latencyMs: performance.now() - window.__submitted,
      rendered: [...document.querySelectorAll("[data-evidence-id]")].map(
        (el) => ({
          id: el.getAttribute("data-evidence-id"),
          text: el.querySelector("blockquote").textContent,
          url: el.querySelector("h3 a").href,
        }),
      ),
      comparison: [...document.querySelectorAll("[data-comparison-id]")].map(
        (el) => ({
          id: el.getAttribute("data-comparison-id"),
          text: el.querySelector("blockquote").textContent,
          url: el.querySelector("h3 a").href,
        }),
      ),
      comparisonNote:
        document.querySelector('[data-testid="comparison-evidence"]')
          ?.textContent ?? null,
    };
  });
  assert(data.answer, "Browser answer event missing");
  assert.equal(data.rendered.length, data.answer.passages.length);
  for (const [i, p] of data.answer.passages.entries()) {
    assert.equal(data.rendered[i].id, p.id);
    assert.equal(data.rendered[i].text, p.text);
    assert.equal(data.rendered[i].url, p.url);
  }
  assert.equal(
    data.comparison.length,
    (data.answer.comparisonPassages ?? []).length,
  );
  for (const [i, p] of (data.answer.comparisonPassages ?? []).entries()) {
    assert.equal(data.comparison[i].id, p.id);
    assert.equal(data.comparison[i].text, p.text);
    assert.equal(data.comparison[i].url, p.url);
  }
  if (data.answer.status === "comparison")
    assert(
      data.comparisonNote.includes(
        "Bu soru birden fazla kararın karşılaştırılmasını gerektiriyor; ilgili kararlar tarih sırasıyla aşağıda.",
      ),
    );
  return {
    ...gradeEvidence(q, data.answer, originals),
    latencyMs: data.latencyMs,
  };
}
function times(rows) {
  const sorted = rows.map((r) => r.latencyMs).sort((a, b) => a - b);
  return {
    n: sorted.length,
    medianMs: sorted[Math.floor(sorted.length / 2)],
    p95Ms: sorted[Math.ceil(sorted.length * 0.95) - 1],
    maxMs: sorted.at(-1),
  };
}
try {
  for (const q of gold.questions) {
    const { page, context } = await open();
    report.cold.push(await ask(page, q));
    await context.close();
    await save();
    console.log(`Cold ${q.id}: ${Math.round(report.cold.at(-1).latencyMs)} ms`);
  }
  const warm = await open();
  // Warm the complete archive once; this setup query is excluded from the warm metric.
  await ask(warm.page, {
    id: "setup",
    question: "inflation",
    filters: {},
    goldEvidence: [],
  });
  for (const q of gold.questions) {
    report.warm.push(await ask(warm.page, q));
    await save();
  }
  await warm.context.close();
  const examples = [
    gold.questions.find((q) => q.id === "P11"),
    gold.questions.find(
      (q) => q.category === "country_comparison" && q.id !== "C01",
    ),
    gold.questions.find((q) => q.id === "PN04"),
  ];
  for (const width of [1440, 768, 375])
    for (const theme of ["dark", "light"]) {
      const { page, context } = await open(width, theme);
      for (const q of examples) {
        await ask(page, q);
        const axe = await new AxeBuilder({ page }).analyze();
        const serious = axe.violations.filter((v) =>
          ["serious", "critical"].includes(v.impact),
        );
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth > window.innerWidth,
        );
        await page.screenshot({
          path: resolve(outputPath, `${q.id}-${width}-${theme}.png`),
          fullPage: true,
        });
        report.views.push({ id: q.id, width, theme, overflow, serious });
      }
      await page.getByText("Refine sources", { exact: true }).click();
      const filterAxe = await new AxeBuilder({ page }).analyze();
      report.views.push({
        id: "open-filters",
        width,
        theme,
        overflow: await page.evaluate(
          () => document.documentElement.scrollWidth > window.innerWidth,
        ),
        serious: filterAxe.violations.filter((v) =>
          ["serious", "critical"].includes(v.impact),
        ),
      });
      await context.close();
      await save();
    }
  report.summary = {
    cold: summarizeEvidence(report.cold),
    warm: summarizeEvidence(report.warm),
    coldLatency: times(report.cold),
    warmLatency: times(report.warm),
    externalRequests: report.requests.filter(
      (u) => new URL(u).origin !== target.origin,
    ),
    overflowViews: report.views.filter((v) => v.overflow).length,
    seriousAccessibilityViews: report.views.filter((v) => v.serious.length)
      .length,
    completed: true,
  };
  console.log(JSON.stringify(report.summary));
} catch (e) {
  report.errors.push(String(e));
  throw e;
} finally {
  await save();
  await browser.close();
}
