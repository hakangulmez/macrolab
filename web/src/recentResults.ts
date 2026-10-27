import type { AnalysisConfig } from "./types";

export const recentResultsKey = "macrolab-recent-results-v1";
export const recentResultsLimit = 5;
export interface RecentResult {
  config: AnalysisConfig;
  completedAt: string;
}
export function readRecentResults(
  valid: (config: unknown) => boolean,
): RecentResult[] {
  try {
    const raw = localStorage.getItem(recentResultsKey);
    if (!raw || raw.length > 1_000_000) return [];
    const entries: unknown = JSON.parse(raw);
    if (!Array.isArray(entries)) return [];
    return entries
      .filter(
        (entry): entry is RecentResult =>
          Boolean(entry) &&
          typeof entry === "object" &&
          typeof entry.completedAt === "string" &&
          Number.isFinite(Date.parse(entry.completedAt)) &&
          valid(entry.config),
      )
      .slice(0, recentResultsLimit);
  } catch {
    return [];
  }
}
export function rememberResult(
  previous: RecentResult[],
  config: AnalysisConfig,
  completedAt = new Date().toISOString(),
): RecentResult[] {
  const key = JSON.stringify(config);
  const next = [
    { config: structuredClone(config), completedAt },
    ...previous.filter((entry) => JSON.stringify(entry.config) !== key),
  ].slice(0, recentResultsLimit);
  try {
    localStorage.setItem(recentResultsKey, JSON.stringify(next));
  } catch {
    // The session list still works when browser storage is blocked or full.
  }
  return next;
}
