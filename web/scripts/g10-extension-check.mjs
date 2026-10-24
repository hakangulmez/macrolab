/* global window, document, requestAnimationFrame */
import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";

export async function checkExtension(
  page,
  name,
  out,
  root,
  AxeBuilder,
  report,
) {
  if (!["monetary_policy", "tur_pass_through"].includes(name)) return;
  const hd = name === "monetary_policy",
    key = hd ? "hd" : "crisis";
  const panel = page.getByTestId(hd ? "hd-view" : "crisis-view");
  const times = [];
  const screenshotDir = join(
    root,
    "docs/screenshots",
    process.env.MACROLAB_SCREENSHOT_GATE ?? out.split("/").at(-1),
  );
  let value;
  for (let i = 0; i < Number(process.env.MACROLAB_EXTENSION_RUNS ?? 5); i++) {
    const n = await page.evaluate(() => window.g7Runs.length),
      start = Date.now();
    await panel
      .getByRole("button", {
        name: hd
          ? "Compute historical decomposition"
          : "Compute crisis analysis",
        exact: true,
      })
      .click();
    await page.waitForFunction((n) => window.g7Runs.length > n, n);
    await panel
      .getByRole("button", { name: "Extension CSV", exact: true })
      .waitFor();
    if (hd) await panel.locator("canvas").waitFor();
    await page.evaluate(
      () =>
        new Promise((r) =>
          requestAnimationFrame(() => requestAnimationFrame(r)),
        ),
    );
    times.push(Date.now() - start);
    value = await page.evaluate(() => window.g7Runs.at(-1));
  }
  assert.equal(value.status, "ok");
  const panelText = await panel.innerText();
  if (hd) {
    const precise =
      value.results[0].historical_decomposition.maximum_identity_error;
    assert(panelText.includes(precise.toExponential(1).replace("e-", "e−")));
    assert(!panelText.includes(String(precise)));
  } else {
    assert(!panelText.includes("(existing row)"));
    assert(panelText.includes("Ratio range (including baseline)"));
    assert(panelText.includes("changes the answer materially"));
    assert(panelText.includes("not a significance test"));
    for (const summary of value.crisis_analysis.agreement) {
      const baseline = value.results[0].pass_through.horizons.find(
        (p) => p.horizon === summary.horizon,
      ).ratio;
      const ratios = [baseline, ...summary.variants.map((v) => v.ratio)];
      assert.equal(summary.ratio_min, Math.min(...ratios));
      assert.equal(summary.ratio_max, Math.max(...ratios));
      for (const variant of summary.variants)
        assert.equal(
          variant.changes_answer_materially,
          Math.abs(variant.ratio - baseline) > 0.5 * Math.abs(baseline),
        );
    }
    for (const horizon of [6, 12, 24]) {
      const summary = value.crisis_analysis.agreement.find(
        (r) => r.horizon === horizon,
      );
      assert(
        summary.variants.find((v) => v.variant_id === "crisis_exclude")
          .changes_answer_materially,
      );
      const row = panel
        .locator("table")
        .first()
        .getByRole("row")
        .filter({ hasText: "Exclude crisis footprints" })
        .filter({
          has: page.getByRole("cell", { name: String(horizon), exact: true }),
        });
      assert((await row.innerText()).includes("changes the answer materially"));
    }
  }
  const native = JSON.parse(
    await readFile(
      join(
        process.env.MACROLAB_ACCEPTED_DIR
          ? join(root, process.env.MACROLAB_ACCEPTED_DIR)
          : out,
        key +
          (process.env.MACROLAB_ACCEPTED_DIR &&
          process.env.MACROLAB_REFERENCE_KIND !== "native"
            ? ".browser.json"
            : ".json"),
      ),
    ),
  );
  let max = 0,
    count = 0;
  function compare(x, y, path = "") {
    if (typeof x === "number") {
      const d = Math.abs(x - y);
      assert(
        d <=
          Number(
            process.env.MACROLAB_PARITY_TOLERANCE ??
              (process.env.MACROLAB_ACCEPTED_DIR ? 0 : 1e-8),
          ),
        `${path}: ${x} / ${y}`,
      );
      max = Math.max(max, d);
      count++;
    } else if (Array.isArray(x)) {
      assert.equal(x.length, y.length, path);
      x.forEach((v, i) => compare(v, y[i], path + "/" + i));
    } else if (x && typeof x === "object") {
      for (const k of Object.keys(x)) {
        if (["runtime_ms", "code_version", "config_hash"].includes(k)) continue;
        compare(x[k], y[k], path + "/" + k);
      }
    } else assert.deepEqual(x, y, path);
  }
  compare(native, value);
  await writeFile(
    join(out, key + ".browser.json"),
    JSON.stringify(value) + "\n",
  );
  const ordered = [...times].sort((a, b) => a - b);
  report.extensions ??= [];
  report.extensions.push({
    name: key,
    max_difference: max,
    numeric_fields: count,
    times_ms: times,
    median_ms: ordered[Math.floor(ordered.length / 2)],
    p90_ms:
      ordered.length === 5
        ? ordered[3] * 0.4 + ordered[4] * 0.6
        : ordered.at(-1),
  });
  for (const format of ["CSV", "Python", "JSON"]) {
    const event = page.waitForEvent("download");
    await panel
      .getByRole("button", { name: "Extension " + format, exact: true })
      .click();
    const d = await event;
    await d.saveAs(
      join(
        out,
        "downloads",
        key + "." + (format === "Python" ? "py" : format.toLowerCase()),
      ),
    );
  }
  for (const width of [1440, 375]) {
    await page.setViewportSize({ width, height: 1000 });
    await panel.scrollIntoViewIfNeeded();
    if (!process.env.MACROLAB_NO_SCREENSHOTS) {
      await mkdir(screenshotDir, { recursive: true });
      await panel.screenshot({
        path: join(screenshotDir, key + "-" + width + ".png"),
      });
    }
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
      "extension overflow",
    );
    const axe = await new AxeBuilder({ page }).analyze();
    report.accessibility.push({
      name: key,
      width,
      violations: axe.violations
        .filter((v) => ["serious", "critical"].includes(v.impact))
        .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
    });
  }
  if (hd) {
    const select = panel.getByLabel("HD variable", { exact: true });
    const options = await select
      .locator("option")
      .evaluateAll((nodes) => nodes.map((n) => n.value));
    for (const v of options) {
      await select.selectOption(v);
      const event = page.waitForEvent("download");
      await panel.getByRole("button", { name: /Export PNG:/ }).click();
      const d = await event;
      await d.saveAs(join(out, "downloads", "hd-" + v + ".png"));
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  console.log("extension", key, JSON.stringify(report.extensions.at(-1)));
}
