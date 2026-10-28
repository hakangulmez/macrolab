import {
  relationshipEligible,
  forecastViewData,
  relationshipExtent,
} from "../additionalViewData";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { usePrimaryChart } from "./PrimaryChart";
import * as echarts from "echarts/core";
import { LineChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  AriaComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsCoreOption } from "echarts/core";
import { chartTheme, escapeHtml, useTheme } from "../theme";
import { niceScale, tickLabel } from "../chartScale";
import { buildVersion } from "../version";
import { buildBundle, type AnalysisRuntime } from "../runtime";
import { csv, download, record, records, text, title } from "../format";
import { resultUnit } from "../resultData";
import { countryIndicators } from "../displayLabels";
import type {
  AnalysisConfig,
  AnalysisResult,
  CountryResult,
  JsonRecord,
  Manifest,
} from "../types";
import { DataTable, Field } from "./Common";
import { analysisErrorMessage } from "../analysisErrors";
import { canonicalChartImage } from "../additionalPngExport";
echarts.use([
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  AriaComponent,
  CanvasRenderer,
]);

function ViewChart({
  name,
  summary,
  xTitle,
  yTitle,
  option,
  legend,
  rows,
  snapshot,
  exportWidth = 966,
  primary = false,
  controls,
}: {
  name: string;
  summary: string;
  xTitle: string;
  yTitle: string;
  option: EChartsCoreOption;
  legend: string[];
  rows: JsonRecord[];
  snapshot: string;
  exportWidth?: 966 | 916;
  primary?: boolean | number;
  controls?: ReactNode;
}) {
  const primaryTarget = usePrimaryChart(primary);
  const ref = useRef<HTMLDivElement>(null),
    instance = useRef<echarts.EChartsType | null>(null),
    theme = useTheme();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!ref.current) return;
    const palette = chartTheme(theme);
    const c = echarts.init(ref.current, palette, { renderer: "canvas" });
    instance.current = c;
    const css = getComputedStyle(document.documentElement);
    const muted = css.getPropertyValue("--muted").trim();
    const border = css.getPropertyValue("--border").trim();
    const styledAxis = (value: unknown) => {
      const a = record(value);
      return {
        ...a,
        nameTextStyle: { color: muted, fontSize: 11 },
        axisLine: { lineStyle: { color: border, width: 1 } },
        axisTick: { show: false },
        axisLabel: {
          ...record(a.axisLabel),
          color: muted,
          fontSize: 10,
          hideOverlap: true,
        },
        splitLine: {
          show: a.type === "value",
          lineStyle: { color: border, type: "dashed", width: 1 },
        },
      };
    };
    c.setOption({
      animation: false,
      aria: {
        enabled: true,
        description: `${name}. ${summary}. X: ${xTitle}. Y: ${yTitle}.`,
      },
      grid: { top: 50, left: 68, right: 22, bottom: 85 },
      ...option,
      xAxis: styledAxis(option.xAxis),
      yAxis: styledAxis(option.yAxis),
    });
    const observer = new ResizeObserver(() => c.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      instance.current = null;
      c.dispose();
    };
  }, [theme, option, name, summary, xTitle, yTitle, primaryTarget]);
  const palette = chartTheme(theme);
  const colors = Array.isArray(option.color)
    ? (option.color as string[])
    : palette.color;
  const legendItems = legend.map((label, i) => {
    const series = records(option.series)[i] ?? {};
    const line = record(series.lineStyle),
      item = record(series.itemStyle);
    return {
      label,
      color: String(item.color ?? line.color ?? colors[i % colors.length]),
      point: series.type === "scatter",
      dashed: line.type === "dashed",
      marker: series.showSymbol !== false && series.type === "line",
    };
  });
  const figure = (
    <figure
      className="card stack additional-view"
      data-testid="additional-chart"
    >
      {controls && <div className="row chart-controls">{controls}</div>}
      <h3>{name}</h3>
      <p className="small">
        X: {xTitle} · Y: {yTitle}
      </p>
      <div className="row" aria-label="Chart series">
        {legendItems.map((item) => (
          <span
            key={item.label}
            className="view-legend-entry"
            data-line-style={
              item.point ? "point" : item.dashed ? "dashed" : "solid"
            }
          >
            <i
              aria-hidden="true"
              className={`view-legend-swatch ${item.point ? "point" : "line"}${item.marker ? " marker" : ""}`}
              style={{
                color: item.color,
                borderTopStyle: item.dashed ? "dashed" : "solid",
              }}
            />
            {item.label}
          </span>
        ))}
      </div>
      <div
        ref={ref}
        style={{ height: 340, width: "100%", minWidth: 0 }}
        role="img"
        aria-label={`${name}. ${summary}`}
      />
      <figcaption className="small">{summary}</figcaption>
      <div className="row">
        <button
          onClick={() =>
            download(
              csv([
                Object.keys(rows[0] ?? {}),
                ...rows.map((r) => Object.values(r)),
              ]),
              `${name}.csv`,
              "text/csv",
            )
          }
        >
          Download chart data
        </button>
        <button
          data-chart-export="png"
          onClick={() => {
            setError("");
            try {
              const c = instance.current;
              if (!c) return;
              const img = new Image();
              img.onload = () => {
                const canvas = document.createElement("canvas");
                canvas.width = Math.max(img.width, 900);
                const measure = canvas.getContext("2d")!;
                measure.font = "16px sans-serif";
                const lines = (value: string) => {
                  const rows: string[] = [];
                  let line = "";
                  for (const word of value.split(" ")) {
                    if (
                      measure.measureText(line + " " + word).width >
                      canvas.width - 48
                    ) {
                      rows.push(line);
                      line = word;
                    } else line += (line ? " " : "") + word;
                  }
                  if (line) rows.push(line);
                  return rows;
                };
                const note = lines(summary),
                  legendLines = lines(
                    legend.map((label) => `━━ ${label}`).join("   ·   "),
                  );
                const top = 110 + legendLines.length * 22;
                canvas.height = img.height + top + 80 + note.length * 22;
                const ctx = canvas.getContext("2d")!;
                ctx.fillStyle = theme === "dark" ? "#131816" : "#ffffff";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, (canvas.width - img.width) / 2, top);
                ctx.fillStyle = theme === "dark" ? "#f1f4ef" : "#17231b";
                ctx.font = "24px sans-serif";
                ctx.fillText(name, 24, 34);
                ctx.font = "16px sans-serif";
                ctx.fillText(`${xTitle} · ${yTitle}`, 24, 64);
                let lx = 24,
                  ly = 96;
                legendItems.forEach((item) => {
                  const width = 36 + ctx.measureText(item.label).width + 18;
                  if (lx + width > canvas.width - 24) {
                    lx = 24;
                    ly += 22;
                  }
                  ctx.strokeStyle = item.color;
                  ctx.fillStyle = item.color;
                  ctx.lineWidth = 2;
                  ctx.setLineDash(item.dashed ? [6, 4] : []);
                  if (!item.point) {
                    ctx.beginPath();
                    ctx.moveTo(lx, ly - 5);
                    ctx.lineTo(lx + 26, ly - 5);
                    ctx.stroke();
                  }
                  ctx.setLineDash([]);
                  if (item.point || item.marker) {
                    ctx.beginPath();
                    ctx.arc(lx + 13, ly - 5, 3, 0, 2 * Math.PI);
                    ctx.fill();
                  }
                  ctx.fillStyle = theme === "dark" ? "#f1f4ef" : "#17231b";
                  ctx.fillText(item.label, lx + 36, ly);
                  lx += width;
                });
                ctx.fillStyle = theme === "dark" ? "#f1f4ef" : "#17231b";
                note.forEach((line, i) =>
                  ctx.fillText(line, 24, top + img.height + 24 + i * 22),
                );
                ctx.fillText(
                  `${buildVersion} · Snapshot ${snapshot} · Existing estimates; no refit`,
                  24,
                  canvas.height - 24,
                );
                const a = document.createElement("a");
                a.href = canvas.toDataURL("image/png");
                a.download = name + ".png";
                a.click();
              };
              img.src = canonicalChartImage(
                c,
                exportWidth,
                theme === "dark" ? "#131816" : "#ffffff",
              );
            } catch (e) {
              setError(analysisErrorMessage(e));
            }
          }}
        >
          Download chart PNG
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      <details>
        <summary>Show new chart data</summary>
        <DataTable rows={rows} />
      </details>
    </figure>
  );
  return primaryTarget ? createPortal(figure, primaryTarget) : figure;
}
const axis = (values: number[], name: string, dataRange = false) => {
  const a = dataRange ? relationshipExtent(values) : niceScale(values);
  return {
    type: "value",
    min: a.min,
    max: a.max,
    interval: a.step,
    name,
    nameLocation: "middle",
    nameGap: 36,
    axisLabel: { formatter: (v: number) => tickLabel(v, a.step) },
    splitLine: { show: true },
  };
};
function Relationship({
  config,
  result,
  manifest,
  runtime,
}: {
  config: AnalysisConfig;
  result: CountryResult;
  manifest: Manifest;
  runtime: AnalysisRuntime;
}) {
  const [data, setData] = useState<JsonRecord | null>(null),
    [error, setError] = useState("");
  const [highlight, setHighlight] = useState("");
  const theme = useTheme();
  useEffect(() => {
    let active = true;
    void buildBundle(config)
      .then((b) => runtime.relationship(config, b, result))
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(analysisErrorMessage(e));
      });
    return () => {
      active = false;
    };
  }, [config, result, runtime]);
  if (error) return <p role="alert">Relationship view: {error}</p>;
  if (!data)
    return (
      <p role="status">
        Preparing the relationship view from the recorded estimation sample…
      </p>
    );
  const points = records(data.points),
    pooled = Boolean(data.pooled),
    indicators = countryIndicators(
      manifest.indicators,
      pooled ? "EA" : result.country,
    );
  const axisLabel = (id: string) => {
    const spec = config.series.find((v) => v.concept_id === id)!;
    const short: Record<string, string> = {
      unemp: "Unemployment",
      gdp_real: "Real GDP",
      cpi: title("cpi", indicators).split(" · ")[0],
    };
    const baseUnit = resultUnit(result, id, indicators);
    const units: Record<string, string> = {
      yoy_pct: "% y/y",
      yoy_diff: `${baseUnit} y/y`,
      qoq_saar: "% annualised",
      log_diff: "% growth",
      hp_cycle: spec.transform_params?.log
        ? "100 × log gap"
        : id === "unemp"
          ? "pp gap"
          : `${baseUnit} gap`,
      hamilton_cycle: `${baseUnit} gap`,
      log: "log level",
    };
    const unit = units[spec.transform] ?? baseUnit;
    return `${short[id] ?? title(id, indicators).split(" · ")[0]} (${unit})`;
  };
  const xTitle = axisLabel(text(data.x_id)),
    yTitle = axisLabel(text(data.y_id)),
    groups = pooled
      ? highlight
        ? ["", highlight]
        : [""]
      : ["Before 2020", "2020 onward"];
  const countries = [...new Set(points.map((p) => text(p.country)))];
  const palette = chartTheme(theme);
  const muted = theme === "dark" ? "#8F96A6" : "#737B89";
  const groupName = (g: string) =>
    pooled
      ? g
        ? name(g)
        : highlight
          ? "Other countries"
          : "All countries"
      : g;
  const name = (c: string) =>
    manifest.countries.find((v) => v.iso3 === c)?.name ?? c;
  const xs = points.map((p) => Number(p.x)),
    ys = points.map((p) => Number(p.y)),
    lo = Math.min(...xs),
    hi = Math.max(...xs);
  const sampleText = `${points.length} observations · ${points.map((p) => text(p.period)).sort()[0]}–${points
    .map((p) => text(p.period))
    .sort()
    .at(-1)}. `;
  const summary =
    sampleText +
    (pooled
      ? "Actual pooled estimation sample. Country fixed effects are partialled out by demeaning within country; the accepted contributions of other regressors (including y/y Brent growth) are removed from the outcome. The line uses the existing pooled unemployment-gap slope, not a new fit. The HP gap is two-sided."
      : "Actual estimation sample; points are coloured before/after 2020. The line uses the existing OLS coefficients, with any additional controls held at their sample means. Association, not causation.");
  const option: EChartsCoreOption = {
    color: pooled
      ? [...groups.map((g) => (g ? palette.color[1] : muted)), palette.color[0]]
      : palette.color,
    xAxis: axis(xs, xTitle, true),
    yAxis: {
      ...axis(
        [
          ...ys,
          Number(data.intercept) + Number(data.slope) * lo,
          Number(data.intercept) + Number(data.slope) * hi,
        ],
        yTitle,
        true,
      ),
      nameLocation: "middle",
      nameGap: 48,
    },
    tooltip: {
      trigger: "item",
      formatter: (p: unknown) => {
        const r = record(p),
          d = record(r.data);
        return d.period
          ? `${escapeHtml(name(text(d.country)))} · ${escapeHtml(text(d.period))}<br/>x: ${escapeHtml(String(d.x))}<br/>y: ${escapeHtml(String(d.y))}`
          : escapeHtml(text(r.seriesName));
      },
    },
    series: [
      ...groups.map((g) => ({
        name: groupName(g),
        type: "scatter",
        symbol: "circle",
        itemStyle: pooled
          ? { color: g ? palette.color[1] : muted, opacity: g ? 1 : 0.55 }
          : undefined,
        symbolSize: 6,
        data: points
          .filter((p) =>
            pooled
              ? g
                ? p.country === g
                : p.country !== highlight
              : text(p.period).slice(0, 4) >= "2020" === (g === "2020 onward"),
          )
          .map((p) => ({ ...p, value: [p.x, p.y] })),
      })),
      {
        name: pooled ? "Existing pooled slope" : "Existing OLS line",
        type: "line",
        showSymbol: false,
        lineStyle: { width: 2, ...(pooled ? { color: palette.color[0] } : {}) },
        data: [lo, hi].map((x) => [
          x,
          Number(data.intercept) + Number(data.slope) * x,
        ]),
      },
    ],
  };
  const heading = pooled
    ? "Pooled Phillips relationship"
    : `${name(result.country)} · ${text(data.x_id) === "gdp_real" && text(data.y_id) === "unemp" ? "Okun relationship" : text(data.y_id) === "cpi" && text(data.x_id) === "unemp" ? "Phillips relationship" : "OLS relationship"}`;
  return (
    <section className="stack" aria-label={heading}>
      <ViewChart
        primary={10}
        controls={
          pooled && (
            <Field label="Highlight">
              <select
                aria-label="Highlight country"
                value={highlight}
                onChange={(e) => setHighlight(e.target.value)}
              >
                <option value="">None</option>
                {countries.map((c) => (
                  <option key={c} value={c}>
                    {name(c)}
                  </option>
                ))}
              </select>
            </Field>
          )
        }
        name={heading}
        xTitle={xTitle}
        yTitle={yTitle}
        summary={summary}
        legend={[
          ...groups.map(groupName),
          pooled ? "Existing pooled slope" : "Existing OLS line",
        ]}
        option={option}
        rows={points}
        snapshot={config.snapshot_id}
      />
    </section>
  );
}
export function RelationshipViews({
  result,
  manifest,
  runtime,
}: {
  result: AnalysisResult;
  manifest: Manifest;
  runtime: AnalysisRuntime;
}) {
  return (
    <>
      {result.results
        .filter((r) => relationshipEligible(result.config, r))
        .map((r) => (
          <Relationship
            key={r.country}
            config={result.config}
            result={r}
            manifest={manifest}
            runtime={runtime}
          />
        ))}
    </>
  );
}

export function ForecastViews({
  result,
  snapshot,
  manifest,
}: {
  result: CountryResult;
  snapshot: string;
  manifest: Manifest;
}) {
  const [h, setH] = useState(1);
  const theme = useTheme();
  const e = record(result.evaluation);
  if (!result.evaluation || result.status !== "ok") return null;
  const horizons = e.horizons as number[],
    selectedHorizon = horizons.includes(h) ? h : horizons[0];
  const outcome = title(
    text(e.target),
    countryIndicators(manifest.indicators, result.country),
  ).split(" · ")[0];
  const { rows, metrics, models } = forecastViewData(result, selectedHorizon),
    unit = text(e.unit, "original units");
  const names = ["Actual", ...models];
  const actualOption: EChartsCoreOption = {
    color: [
      theme === "dark" ? "#EEF1F6" : "#11151C",
      ...chartTheme(theme).color,
    ],
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: rows.map((r) => r.Period),
      name: "Target period",
      nameLocation: "middle",
      nameGap: 36,
      axisLabel: { rotate: 35 },
    },
    yAxis: {
      ...axis(
        rows
          .flatMap((r) => names.map((n) => Number(r[n as keyof typeof r])))
          .filter(Number.isFinite),
        outcome,
      ),
      nameLocation: "end",
      nameGap: 15,
    },
    series: names.map((name) => ({
      name,
      type: "line",
      showSymbol: false,
      connectNulls: false,
      lineStyle: {
        width: name === "Actual" ? 3 : 1.6,
        type: name === "Random walk" ? "dashed" : "solid",
      },
      data: rows.map((r) => r[name as keyof typeof r] ?? null),
    })),
  };
  const metricRows: JsonRecord[] = horizons.map((h) => ({
    Horizon: h,
    ...Object.fromEntries(
      models.map((m) => [
        m,
        metrics.find((r) => r.horizon === h && r.model === m)?.rmse ?? null,
      ]),
    ),
  }));
  const metricOption: EChartsCoreOption = {
    tooltip: { trigger: "axis" },
    xAxis: {
      ...axis(
        horizons,
        `Horizon (${result.actual_sample.frequency === "M" ? "months" : "quarters"})`,
        true,
      ),
      minInterval: 1,
      interval: 1,
      min: Math.min(...horizons),
      max: Math.max(...horizons),
      axisLabel: {
        formatter: (v: number) => (horizons.includes(v) ? String(v) : ""),
      },
    },
    yAxis: {
      ...axis(
        metrics.map((r) => Number(r.rmse)),
        "RMSE",
      ),
      nameLocation: "end",
      nameGap: 15,
    },
    series: models.map((m) => ({
      name: m,
      type: "line",
      symbol: "circle",
      clip: false,
      symbolSize: 7,
      lineStyle: {
        width: m === "Random walk" ? 3 : 2,
        type: m === "Random walk" ? "dashed" : "solid",
      },
      data: metricRows.map((r) => [r.Horizon, r[m] ?? null]),
    })),
  };
  return (
    <section className="stack" data-testid="forecast-extra-views">
      <h2>Forecast paths and errors</h2>
      <Field label="Forecast-path horizon">
        <select
          value={selectedHorizon}
          onChange={(event) => setH(Number(event.target.value))}
        >
          {horizons.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <ViewChart
        name={`Actual vs forecasts · ${outcome} · horizon ${selectedHorizon}`}
        exportWidth={916}
        xTitle="Target period"
        yTitle={unit}
        summary="Pseudo-out-of-sample, final-vintage data; real-time performance may be worse. Each point uses the recorded forecast for this horizon, made at its displayed origin. Missing/failed origins remain absent; no new forecast is fitted."
        option={actualOption}
        legend={names}
        rows={rows}
        snapshot={snapshot}
      />
      <ViewChart
        primary={10}
        name="RMSE by horizon"
        exportWidth={916}
        xTitle={`Forecast horizon (${result.actual_sample.frequency === "M" ? "months" : "quarters"})`}
        yTitle={unit}
        summary="Recorded RMSE on paired common origins for each horizon; lower is better. Random walk is the reference. The scoring samples can differ across horizons."
        option={metricOption}
        legend={models}
        rows={metricRows}
        snapshot={snapshot}
      />
    </section>
  );
}
