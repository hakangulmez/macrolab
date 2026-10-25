import { buildVersion } from "./version";
import type { AnalysisResult, Manifest, JsonRecord } from "./types";
import { chartData, termLabel } from "./resultData";
import { records, text } from "./format";
/** Presentation serializer only: values are copied, never re-estimated or rounded. */
export function latexEscape(value: unknown): string {
  return text(value, "").replace(
    /[\\{}$&#%_^~]/g,
    (c) =>
      ({
        "\\": "\\textbackslash{}",
        "{": "\\{",
        "}": "\\}",
        $: "\\$",
        "&": "\\&",
        "#": "\\#",
        "%": "\\%",
        _: "\\_",
        "^": "\\textasciicircum{}",
        "~": "\\textasciitilde{}",
      })[c]!,
  );
}
export function latexTables(
  result: AnalysisResult,
  manifest: Manifest,
): string {
  const blocks = result.results.map((r) => {
    let rows: JsonRecord[], columns: string[];
    if (r.evaluation) {
      rows = records((r.evaluation as JsonRecord).metrics);
      columns = [
        "model",
        "horizon",
        "rmse",
        "mae",
        "relative_rmse",
        "n_forecasts",
      ];
    } else if (r.coefficients_table?.length) {
      rows = r.coefficients_table.map((c) => ({
        ...c,
        term: termLabel(c.term, manifest.indicators),
      }));
      columns = ["term", "estimate", "std_error", "lower", "upper"];
    } else {
      rows = chartData(r, manifest.indicators).flatMap((c) =>
        c.points.map((p) => ({
          response: c.name,
          period: p.period,
          estimate: p.value,
          lower: p.lower,
          upper: p.upper,
        })),
      );
      columns = ["response", "period", "estimate", "lower", "upper"];
    }
    const name =
      manifest.countries.find((c) => c.iso3 === r.country)?.name ?? r.country;
    return `% ${name}; model ${r.model_id}; actual sample ${r.actual_sample.start} to ${r.actual_sample.end}; n=${r.actual_sample.nobs}\n\\begin{longtable}{${columns.map(() => "l").join("")}}\n${columns.map(latexEscape).join(" & ")} \\\\\n\\hline\n${rows.map((row) => columns.map((c) => latexEscape(row[c])).join(" & ") + " \\\\").join("\n")}\n\\end{longtable}`;
  });
  return `% MacroLab ${buildVersion}; scientific runtime ${result.code_version}; snapshot ${result.snapshot_id}; config ${result.config_hash}\n% Full-precision existing result fields; no inference is recomputed. Requires longtable.\n\\documentclass{article}\n\\usepackage[T1]{fontenc}\n\\usepackage[a4paper,landscape,margin=1.5cm]{geometry}\n\\usepackage{longtable}\n\\begin{document}\n\\small\n${blocks.join("\n\n")}\n\\end{document}\n`;
}
