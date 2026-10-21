import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
// Playwright creates both its browser profile and download/artifact scratch space here.
process.env.TMPDIR = join(root, ".cache/tmp");
const require = createRequire(import.meta.url);
const { chromium } = require("../web/node_modules/@playwright/test");
const bootOnly = process.argv.includes("--boot-only");
const fixturePath = join(root, "runs/g2/browser_fixture.json");
const wheel = JSON.parse(
  await readFile(join(root, "runs/g2/runtime_wheel.json")),
);
const fixture = bootOnly ? null : JSON.parse(await readFile(fixturePath));
const assets = JSON.parse(
  await readFile(join(root, "runs/g2/runtime_assets.json")),
);
const fileHash = async (path) =>
  createHash("sha256")
    .update(await readFile(path))
    .digest("hex");
async function changedSources() {
  const changed = [];
  for (const [name, expected] of Object.entries(wheel.source_files)) {
    if ((await fileHash(join(root, "src", name))) !== expected)
      changed.push(name);
  }
  return changed;
}
if ((await changedSources()).length)
  throw new Error("Python sources changed; rebuild the portable wheel first");
for (const [name, entry] of Object.entries(assets.runtime_files)) {
  if (
    (await fileHash(join(root, assets.local_directory, name))) !== entry.sha256
  )
    throw new Error(`Cached runtime hash differs: ${name}`);
}
for (const [name, entry] of Object.entries(assets.packages)) {
  if (
    (await fileHash(join(root, assets.local_directory, entry.file_name))) !==
    entry.sha256
  )
    throw new Error(`Cached scientific hash differs: ${name}`);
}
const port = await new Promise((resolve, reject) => {
  const socket = createServer();
  socket.on("error", reject);
  socket.listen(0, "127.0.0.1", () => {
    const value = socket.address().port;
    socket.close(() => resolve(value));
  });
});
const origin = `http://127.0.0.1:${port}`;
const arguments_ = ["scripts/g2_browser_server.py", "--port", String(port)];
if (fixture) arguments_.push("--fixture", fixturePath);
const server = spawn(join(root, ".venv/bin/python"), arguments_, {
  cwd: root,
  env: {
    ...process.env,
    TMPDIR: join(root, ".cache/tmp"),
    PYTHONUNBUFFERED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
});
let serverLog = "";
server.stdout.on("data", (chunk) => {
  serverLog += chunk;
});
server.stderr.on("data", (chunk) => {
  serverLog += chunk;
});
let browser;
const requests = [];
const denied = [];
const failures = [];
const results = [];
const started = Date.now();
const deadline = setTimeout(() => {
  failures.push("Runtime validation exceeded its180-second limit");
  void browser?.close();
  server.kill("SIGTERM");
}, 180000);

function compare(
  expected,
  actual,
  path = "$",
  evidence = { max_abs_difference: 0, numeric_values: 0, mismatches: [] },
) {
  if (typeof expected === "number" && typeof actual === "number") {
    evidence.numeric_values += 1;
    const difference = Math.abs(expected - actual);
    if (difference > evidence.max_abs_difference) {
      evidence.max_abs_difference = difference;
      evidence.worst_path = path;
    }
    if (!Number.isFinite(difference))
      evidence.mismatches.push(`${path}: nonfinite difference`);
  } else if (Array.isArray(expected) && Array.isArray(actual)) {
    if (expected.length !== actual.length)
      evidence.mismatches.push(`${path}: array length differs`);
    expected.forEach((item, index) =>
      compare(item, actual[index], `${path}[${index}]`, evidence),
    );
  } else if (
    expected &&
    actual &&
    typeof expected === "object" &&
    typeof actual === "object"
  ) {
    const keys = Object.keys(expected)
      .filter((key) => key !== "runtime_ms")
      .sort();
    const other = Object.keys(actual)
      .filter((key) => key !== "runtime_ms")
      .sort();
    if (JSON.stringify(keys) !== JSON.stringify(other))
      evidence.mismatches.push(`${path}: object keys differ`);
    keys.forEach((key) =>
      compare(expected[key], actual[key], `${path}.${key}`, evidence),
    );
  } else if (expected !== actual) {
    evidence.mismatches.push(
      `${path}: ${JSON.stringify(expected)} != ${JSON.stringify(actual)}`,
    );
  }
  return evidence;
}

try {
  let healthy = false;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (server.exitCode !== null)
      throw new Error(`Local server exited: ${serverLog}`);
    try {
      healthy = (await fetch(`${origin}/health`)).ok;
      if (healthy) break;
    } catch {
      /* local process may still be starting */
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (!healthy)
    throw new Error(`Local server did not become ready: ${serverLog}`);
  browser = await chromium.launch({
    executablePath: join(root, "scripts/local_chrome.sh"),
    headless: true,
    args: [
      "--disable-background-networking",
      "--disable-component-update",
      "--no-first-run",
    ],
  });
  const context = await browser.newContext({ serviceWorkers: "block" });
  await context.route("**/*", async (route) => {
    const url = route.request().url();
    requests.push(url);
    if (new URL(url).origin !== origin) {
      denied.push(url);
      await route.abort("blockedbyclient");
    } else {
      await route.continue();
    }
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => failures.push(String(error)));
  await page.goto(`${origin}/runtime/harness.html`);
  await page.waitForFunction(() => typeof window.runtimeRequest === "function");
  const browserInfo = await page.evaluate(
    async (wheelMetadata) =>
      window.runtimeRequest({
        type: "init",
        indexURL: "/assets/",
        wheelURL: `/artifacts/${wheelMetadata.wheel_file}`,
        wheelSHA256: wheelMetadata.wheel_sha256,
        codeVersion: wheelMetadata.code_version,
      }),
    wheel,
  );
  console.log(
    `Browser Python ${browserInfo.versions.python} initialised in ${browserInfo.initialisation_ms.toFixed(0)}ms`,
  );
  if (fixture) {
    for (const testcase of fixture.cases) {
      const response = await fetch(
        `${origin}${testcase.bundle ? "/live" : ""}/run`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(testcase.config),
        },
      );
      if (!response.ok)
        throw new Error(
          `Local API rejected ${testcase.id}: ${await response.text()}`,
        );
      const native = await response.json();
      const actual = await page.evaluate(
        ({ config, bundle }) =>
          window.runtimeRequest({
            type: "run",
            config,
            bundle,
          }),
        { config: testcase.config, bundle: testcase.bundle ?? fixture.bundle },
      );
      const evidence = compare(native, actual);
      const tolerance = testcase.tolerance ?? 1e-8;
      const passed =
        evidence.max_abs_difference <= tolerance &&
        evidence.mismatches.length === 0 &&
        native.status === "ok" &&
        actual.status === "ok";
      results.push({
        id: testcase.id,
        model_id: testcase.config.model.id,
        ...evidence,
        tolerance,
        passed,
        native_status: native.status,
        browser_status: actual.status,
        config_hash: native.config_hash,
        snapshot_id: native.snapshot_id,
        actual_samples: native.actual_samples,
        native_runtime_ms: native.runtime_ms,
        browser_runtime_ms: actual.runtime_ms,
      });
      console.log(
        `${testcase.id}: ${passed ? "PASS" : "FAIL"}; max difference ${evidence.max_abs_difference}; ${evidence.numeric_values} numbers`,
      );
      if (!passed) {
        await writeFile(
          join(root, "runs/g2/parity_failure.json"),
          JSON.stringify({ case: testcase, native, browser: actual }, null, 2),
        );
      }
    }
    const config = fixture.cases[0].config;
    const native = await fetch(`${origin}/compatibility`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }).then((response) => response.json());
    const actual = await page.evaluate(
      ({ config, bundle }) =>
        window.runtimeRequest({ type: "compatibility", config, bundle }),
      { config, bundle: fixture.bundle },
    );
    const comparison = compare(native, actual);
    results.push({
      id: "compatibility",
      ...comparison,
      passed:
        comparison.max_abs_difference <= 1e-8 &&
        comparison.mismatches.length === 0,
    });
  }
  const changed = await changedSources();
  const evidence = {
    schema_version: 1,
    executed_in: "Google Chrome real Web Worker / Pyodide WebAssembly",
    browser_version: browser.version(),
    temporary_directory: process.env.TMPDIR,
    browser: browserInfo,
    native_versions: fixture?.native_versions,
    wheel,
    source_hashes_unchanged: changed.length === 0,
    changed_sources: changed,
    worker_sha256: await fileHash(join(root, "web/runtime/worker.mjs")),
    assets_verified: assets.all_hashes_verified,
    scientific_total_bytes: assets.scientific_total_bytes,
    fixture: fixture?.description,
    results,
    outbound_requests_blocked: denied,
    observed_requests: requests.map((url) =>
      url.replace(origin, "http://127.0.0.1:<ephemeral-port>"),
    ),
    network_policy:
      "Context routing and worker fetch guard reject all non-local origins",
    ignored_result_fields: ["runtime_ms"],
    page_errors: failures,
    total_ms: Date.now() - started,
    passed:
      results.every((item) => item.passed) &&
      !failures.length &&
      !denied.length &&
      !changed.length,
  };
  await writeFile(
    join(root, `runs/g2/${bootOnly ? "runtime_boot" : "runtime_parity"}.json`),
    JSON.stringify(evidence, null, 2) + "\n",
  );
  if (!evidence.passed) process.exitCode = 1;
} catch (error) {
  console.error(error);
  if (serverLog) console.error(serverLog.slice(-6000));
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  if (browser) await browser.close();
  server.kill("SIGTERM");
  await new Promise((resolve) => {
    if (server.exitCode !== null) resolve();
    else {
      const timer = setTimeout(() => {
        server.kill("SIGKILL");
        resolve();
      }, 5000);
      server.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    }
  });
}
