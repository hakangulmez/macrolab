import type { AnalysisResult, Manifest } from "./types";
import { chartData, type ResultChart } from "./resultData";
import { niceScale } from "./chartScale";
import { record } from "./format";
export function countryPanels(
  result: AnalysisResult,
  manifest: Manifest,
): ResultChart[] {
  const responses = result.results.find((r) => r.irf)?.irf?.variables ?? [];
  return responses.flatMap((response) => {
    const charts = result.results.flatMap((r) =>
      chartData(r, manifest.indicators)
        .filter((c) => c.variable === response)
        .map((c) => {
          const sample = record(
            record(record(r.response_results)[response]).actual_sample ??
              r.actual_sample,
          );
          return {
            ...c,
            name: `${manifest.countries.find((x) => x.iso3 === r.country)?.name ?? r.country} · ${c.name}`,
            transformation: `${c.transformation} · ${sample.start}–${sample.end} · n=${sample.nobs}`,
          };
        }),
    );
    const axis = niceScale(
      charts.flatMap((c) =>
        c.points.flatMap((p) => [p.value, p.lower, p.upper]),
      ),
    );
    return charts.map((c) => ({ ...c, axis }));
  });
}
