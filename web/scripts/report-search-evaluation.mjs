import { readFile } from "node:fs/promises";
import { gunzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { verifiedEvent, periodMatches } from "../src/reportEvidenceDates.ts";

export async function implementationSeal(webRoot) {
  const files = {};
  for (const file of [
    "src/reportSearch.ts",
    "src/reportEvidenceDates.ts",
    "src/reportEvidenceSupport.ts",
    "src/data/report-meeting-catalog.ts",
    "src/reportSearch.worker.ts",
  ]) {
    files[file] = createHash("sha256")
      .update(await readFile(resolve(webRoot, file)))
      .digest("hex");
  }
  return {
    files,
    sha256: createHash("sha256").update(JSON.stringify(files)).digest("hex"),
  };
}

export async function loadEvidencePool(webRoot) {
  const folder = resolve(webRoot, "src/data/report-search");
  const manifest = JSON.parse(await readFile(resolve(folder, "manifest.json")));
  const pool = [];
  for (const shard of manifest.shards) {
    const bytes = await readFile(resolve(folder, shard.file));
    const hash = createHash("sha256").update(bytes).digest("hex");
    if (hash !== shard.sha256) throw new Error(`Bad shard: ${shard.file}`);
    const data = JSON.parse(gunzipSync(bytes));
    if (data.passages.length !== shard.passages)
      throw new Error(`Incomplete shard: ${shard.file}`);
    pool.push(...data.passages);
  }
  return { manifest, pool };
}

export function gradeEvidence(question, answer, poolById) {
  const groups = question.goldEvidence ?? [];
  const chronological = answer.comparisonPassages ?? [];
  const comparison = answer.status === "comparison";
  const sorted = chronological.every(
    (p, i) =>
      !i ||
      (chronological[i - 1].verifiedEventOn ??
        chronological[i - 1].publishedOn) <=
        (p.verifiedEventOn ?? p.publishedOn),
  );
  const scopeCorrect = chronological.every(
    (p) =>
      periodMatches(p, answer.plan.period) &&
      (!answer.plan.institutions.length ||
        answer.plan.institutions.includes(p.institution)) &&
      (!answer.plan.countries.length ||
        answer.plan.countries.includes(p.country)),
  );
  const evidence = comparison ? chronological : answer.passages.slice(0, 5);
  const matched = groups.map((group) =>
    evidence.some(
      (p) =>
        p.country === group.country &&
        (!group.exactPassageId || p.id === group.exactPassageId) &&
        p.publishedOn === group.publishedOn &&
        p.sourceIds.some((id) => group.anyOfChunkIds.includes(id)) &&
        p.text.includes(group.expectedQuote) &&
        (!group.expectedEventOn || p.verifiedEventOn === group.expectedEventOn),
    ),
  );
  const fields = [
    "text",
    "country",
    "institution",
    "publishedOn",
    "eventOn",
    "url",
    "section",
    "speaker",
    "region",
  ];
  return {
    id: question.id,
    question: question.question,
    category: question.category,
    split: question.split,
    expectedGroups: groups.length,
    matchedGroups: matched.filter(Boolean).length,
    hitAt5: groups.length && !comparison ? matched.some(Boolean) : null,
    completeAt5: groups.length && !comparison ? matched.every(Boolean) : null,
    evidenceFormat: comparison
      ? "chronological_source_list"
      : "primary_top_five",
    chronologicalOrderCorrect: sorted,
    comparisonScopeCorrect: scopeCorrect,
    completeUnderRequestedFormat: groups.length
      ? matched.every(Boolean) &&
        (!comparison ||
          (sorted && scopeCorrect && answer.passages.length === 0))
      : null,
    correctNotFound: groups.length
      ? null
      : answer.status === "not_found" &&
        answer.passages.length === 0 &&
        chronological.length === 0,
    sourceIntegrity: [
      ...answer.passages,
      ...chronological,
      ...(answer.relatedPassages ?? []),
    ].every((p) => {
      const original = poolById.get(p.id);
      return (
        original &&
        fields.every((field) => p[field] === original[field]) &&
        p.verifiedEventOn === verifiedEvent(original).date
      );
    }),
    falsePremise: Boolean(
      question.falsePremise || question.category === "false_premise",
    ),
    wrongPeriod:
      !scopeCorrect ||
      !sorted ||
      answer.passages.some((p) => {
        const temporal = groups.filter(
          (g) => g.country === p.country && g.expectedEventOn,
        );
        return (
          temporal.length > 0 &&
          !temporal.some((g) => p.verifiedEventOn === g.expectedEventOn)
        );
      }),
    answer,
    expected: groups,
  };
}

export function summarizeEvidence(rows) {
  const positives = rows.filter((r) => r.expectedGroups);
  const negatives = rows.filter((r) => !r.expectedGroups);
  return {
    questions: rows.length,
    positive: positives.length,
    negative: negatives.length,
    hitAt5: positives.filter((r) => r.hitAt5).length,
    completeAt5: positives.filter((r) => r.completeAt5).length,
    comparisonQuestions: positives.filter(
      (r) => r.evidenceFormat === "chronological_source_list",
    ).length,
    completeUnderRequestedFormat: positives.filter(
      (r) => r.completeUnderRequestedFormat,
    ).length,
    completeEvidenceRate: positives.length
      ? positives.filter((r) => r.completeUnderRequestedFormat).length /
        positives.length
      : null,
    requiredGroups: positives.reduce((n, r) => n + r.expectedGroups, 0),
    matchedGroups: positives.reduce((n, r) => n + r.matchedGroups, 0),
    correctNotFound: negatives.filter((r) => r.correctNotFound).length,
    falsePremiseQuestions: rows.filter((r) => r.falsePremise).length,
    falsePremiseErrors: rows.filter((r) => r.falsePremise && !r.correctNotFound)
      .length,
    wrongPeriodAnswers: rows.filter((r) => r.wrongPeriod).length,
    integrityFailures: rows.filter((r) => !r.sourceIntegrity).length,
    economicMisreadingReview:
      "Requires source-reading review; exact copying alone is not semantic validation.",
  };
}
