/* Run against the caller-owned local Vite preview; never start or stop its server. */
import { createRequire } from "node:module";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
process.env.TMPDIR = join(root, ".cache/tmp");
const require = createRequire(import.meta.url);
const { chromium } = require("../web/node_modules/@playwright/test");
const base = process.env.G3_BASE_URL ?? "http://127.0.0.1:5173/";
const origin = new URL(base).origin;
if (new URL(base).hostname !== "127.0.0.1")
  throw new Error("Use the caller-owned loopback preview");
const gate = process.env.MACROLAB_REVIEW_GATE ?? "g4";
if (!["g3", "g31", "g4"].includes(gate)) throw new Error("Unsupported review gate");
const output = join(root, `runs/${gate}/runtime`);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath:
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
const deadline = setTimeout(() => {
  void browser.close();
}, 180000);
const denied = [];
const requests = [];
try {
  const context = await browser.newContext({ serviceWorkers: "block" });
  await context.route("**/*", async (route) => {
    const url = route.request().url();
    requests.push(url);
    if (new URL(url).origin !== origin) {
      denied.push(url);
      await route.abort("blockedbyclient");
    } else if (route.request().isNavigationRequest() && url === base) {
      // Isolate transport verification from concurrent UI hot-reload navigation.
      await route.fulfill({
        contentType: "text/html",
        body: "<!doctype html><html><head><title>MacroLab runtime verification</title></head><body></body></html>",
      });
    } else await route.continue();
  });
  const page = await context.newPage();
  await page.goto(base);
  const evidence = await page.evaluate(async (reviewGate) => {
    const { AnalysisRuntime, getManifest, buildBundle } =
      await import("/src/runtime.ts");
    const progress = [];
    const runtime = new AnalysisRuntime((text) => progress.push(text));
    const manifest = await getManifest();
    const cases = [];
    try {
      for (const template of manifest.templates) {
        const encoded = await runtime.encode(template.config);
        const decoded = await runtime.decode(encoded);
        const bundle = await buildBundle(decoded);
        const result = await runtime.run(decoded, bundle);
        if (result.status !== "ok")
          throw new Error(`${template.id}: ${JSON.stringify(result.checks)}`);
        const script = await runtime.exportPython(decoded, bundle);
        cases.push({
          id: template.id,
          encoded,
          config: decoded,
          result,
          script,
        });
      }
      const config = manifest.templates.find(
        (item) => item.id === "monetary_policy",
      ).config;
      const benchmark = [];
      if (reviewGate === "g31") {
        const bundle = await buildBundle(config);
        for (let iteration = 0; iteration < 5; iteration += 1) {
          const start = performance.now();
          const result = await runtime.run(config, bundle);
          benchmark.push({iteration:iteration+1, wall_ms:performance.now()-start, engine_ms:result.runtime_ms, config_hash:result.config_hash});
        }
        const precise = structuredClone(config);
        precise.outputs.irf.draws = 1000;
        const start = performance.now();
        const result = await runtime.run(precise, bundle);
        const wall_ms = performance.now()-start;
        const script = await runtime.exportPython(precise, bundle);
        cases.push({id:"monetary_policy_precise",config:precise,result,script,wall_ms});
      }
      const pending = runtime.run(config, await buildBundle(config)).then(
        () => "unexpected completed result",
        (error) => String(error),
      );
      await new Promise((resolve) => setTimeout(resolve, 20));
      runtime.cancel();
      const cancellation = await pending;
      if (!cancellation.includes("Cancelled")) throw new Error(cancellation);
      const restart = manifest.templates.find(
        (item) => item.id === "okuns_law",
      ).config;
      const restarted = await runtime.run(restart, await buildBundle(restart));
      if (restarted.status !== "ok")
        throw new Error("Worker did not recover after cancellation");
      return {
        cases,
        benchmark,
        progress,
        cancellation,
        restarted_status: restarted.status,
        countries: manifest.countries.length,
        indicators: manifest.national_concepts,
        global_factors: manifest.global_factors,
        coverage_cells: manifest.coverage.length,
        reproduction_environment: manifest.runtime.reproduction_environment,
        source_archive_sha256: manifest.runtime.source_archive_sha256,
      };
    } finally {
      runtime.dispose();
    }
  }, gate);
  for (const item of evidence.cases) {
    const scriptPath = join(output, `${item.id}.py`);
    await writeFile(scriptPath, item.script);
    delete item.script;
    const runner =
      "import runpy,socket,sys;socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Network forbidden'));runpy.run_path(sys.argv[1],run_name='__main__')";
    const process = spawnSync(
      join(root, ".venv/bin/python"),
      ["-I", "-c", runner, scriptPath],
      {
        cwd: output,
        env: {
          ...globalThis.process.env,
          TMPDIR: join(root, ".cache/tmp"),
          PYTHONPATH: "",
        },
        encoding: "utf8",
        timeout: 120000,
        maxBuffer: 10 * 1024 * 1024,
      },
    );
    if (process.status !== 0)
      throw new Error(
        `Browser export failed natively: ${item.id}\n${process.stderr}`,
      );
    const native = JSON.parse(process.stdout);
    const comparison = {
      max_abs_difference: 0,
      numerical_values: 0,
      mismatches: [],
    };
    compare(item.result, native, "$", comparison);
    item.export_metadata = native.export_metadata;
    item.comparison = comparison;
    item.passed =
      comparison.max_abs_difference <= 1e-8 && !comparison.mismatches.length;
    console.log(
      `${item.id}: ${item.passed ? "PASS" : "FAIL"} browser-generated standalone export; maxdiff${comparison.max_abs_difference}`,
    );
  }
  evidence.denied_external_requests = denied;
  evidence.requests = requests.map((url) =>
    url.replace(origin, "http://127.0.0.1:<preview>"),
  );
  evidence.browser_version = browser.version();
  evidence.passed =
    !denied.length && evidence.cases.every((item) => item.passed);
  await writeFile(
    join(output, "verification.json"),
    JSON.stringify(evidence, null, 2) + "\n",
  );
  if (!evidence.passed) process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  await browser.close();
}

function compare(expected, actual, path, result) {
  if (typeof expected === "number" && typeof actual === "number") {
    result.numerical_values += 1;
    const difference = Math.abs(expected - actual);
    if (difference > result.max_abs_difference) {
      result.max_abs_difference = difference;
      result.worst_path = path;
    }
    if (!Number.isFinite(difference))
      result.mismatches.push(`${path}: nonfinite`);
  } else if (Array.isArray(expected) && Array.isArray(actual)) {
    if (expected.length !== actual.length)
      result.mismatches.push(`${path}: different lengths`);
    expected.forEach((item, index) =>
      compare(item, actual[index], `${path}[${index}]`, result),
    );
  } else if (
    expected &&
    actual &&
    typeof expected === "object" &&
    typeof actual === "object"
  ) {
    const ignore = new Set(["runtime_ms", "export_metadata"]);
    const keys = Object.keys(expected)
      .filter((key) => !ignore.has(key))
      .sort();
    const other = Object.keys(actual)
      .filter((key) => !ignore.has(key))
      .sort();
    if (JSON.stringify(keys) !== JSON.stringify(other))
      result.mismatches.push(`${path}: different fields`);
    keys.forEach((key) =>
      compare(expected[key], actual[key], `${path}.${key}`, result),
    );
  } else if (expected !== actual)
    result.mismatches.push(
      `${path}: ${JSON.stringify(expected)} != ${JSON.stringify(actual)}`,
    );
}
