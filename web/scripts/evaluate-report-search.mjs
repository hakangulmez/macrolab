import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { EvidenceIndex } from "../src/reportSearch.ts";
import {
  loadEvidencePool,
  gradeEvidence,
  summarizeEvidence,
  implementationSeal,
} from "./report-search-evaluation.mjs";

// Node 26+ runs the pure TypeScript search module without a transpilation step.
const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const [goldPath, outputPath, split = "all"] = process.argv.slice(2);
if (
  !goldPath ||
  !outputPath ||
  !["all", "development", "holdout"].includes(split)
)
  throw new Error(
    "Usage: node scripts/evaluate-report-search.mjs GOLD.json NEW_OUTPUT_DIR [all|development|holdout]",
  );
await mkdir(outputPath, { recursive: false });
const goldBytes = await readFile(goldPath);
const gold = JSON.parse(goldBytes);
const { pool } = await loadEvidencePool(webRoot);
const originals = new Map(pool.map((p) => [p.id, p]));
const index = new EvidenceIndex();
const started = performance.now();
index.add(pool);
const buildMs = performance.now() - started;
const rows = gold.questions
  .filter((q) => split === "all" || q.split === split)
  .map((q) => gradeEvidence(q, index.search(q.question, q.filters), originals));
const summary = {
  ...summarizeEvidence(rows),
  split,
  indexBuildMs: buildMs,
  queryMaxMs: Math.max(...rows.map((r) => r.answer.elapsedMs)),
  goldSha256: createHash("sha256").update(goldBytes).digest("hex"),
  implementationSha256: createHash("sha256")
    .update(await readFile(resolve(webRoot, "src/reportSearch.ts")))
    .digest("hex"),
  latencyScope: "Node computation only; not browser submit-to-render latency.",
  implementationBundle: await implementationSeal(webRoot),
};
await writeFile(
  resolve(outputPath, "results.json"),
  JSON.stringify({ summary, rows }, null, 2) + "\n",
);
console.log(JSON.stringify(summary));
