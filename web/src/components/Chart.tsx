import { useContext, useEffect, useRef, useState } from "react";
import { ChartExportContext } from "../chartExportContext";
import { exportPng, type PngContext } from "../pngExport";
import type { ResultChart } from "../resultData";
import * as echarts from "echarts/core";
import {
  LineChart,
  BarChart,
  ScatterChart,
  CustomChart,
  type CustomSeriesOption,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  AriaComponent,
  MarkLineComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { niceScale, tickLabel, type AxisScale } from "../chartScale";
import { DataTable } from "./Common";
echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  CustomChart,
  GridComponent,
  TooltipComponent,
  AriaComponent,
  MarkLineComponent,
  CanvasRenderer,
]);
export interface ChartPoint {
  period: string | number;
  value: number | null;
  lower?: number;
  upper?: number;
  comparison?: number | null;
  comparisonLower?: number;
  comparisonUpper?: number;
}
export function Chart({
  title,
  unit,
  points,
  summary,
  bar = false,
  coefficient = false,
  comparisonLabel = "Comparison",
  axis,
  intervalLabel = "Pointwise interval",
  exportContext,
  stack,
  pngNote,
}: {
  title: string;
  unit: string;
  points: ChartPoint[];
  summary: string;
  first?: boolean;
  bar?: boolean;
  coefficient?: boolean;
  comparisonLabel?: string;
  axis?: AxisScale;
  intervalLabel?: string;
  exportContext?: PngContext;
  stack?: ResultChart["stack"];
  pngNote?: string;
}) {
  const inherited = useContext(ChartExportContext);
  const context = exportContext ?? inherited;
  const [exportError, setExportError] = useState("");
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current || !points.length) return;
    const css = getComputedStyle(document.documentElement);
    const blue = css.getPropertyValue("--blue").trim(),
      orange = css.getPropertyValue("--orange").trim(),
      muted = css.getPropertyValue("--muted").trim(),
      border = css.getPropertyValue("--border").trim();
    const chart = echarts.init(element.current, undefined, {
      renderer: "canvas",
    });
    const bands = points.some(
      (p) => p.lower !== undefined && p.upper !== undefined,
    );
    const extent = points
      .flatMap((p) => [
        p.value,
        p.lower,
        p.upper,
        p.comparison,
        p.comparisonLower,
        p.comparisonUpper,
      ])
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (stack)
      points.forEach((_, i) =>
        extent.push(
          stack.reduce((s, c) => s + Math.max(0, c.values[i]), 0),
          stack.reduce((s, c) => s + Math.min(0, c.values[i]), 0),
        ),
      );
    const scale = axis ?? niceScale(extent);
    const renderBand =
      (secondary = false): NonNullable<CustomSeriesOption["renderItem"]> =>
      (_params, api) => {
        if (bar || coefficient)
          return {
            type: "group",
            children: points.flatMap((p, i) => {
              if (p.lower === undefined || p.upper === undefined) return [];
              const a = api.coord([i, p.lower]),
                b = api.coord([i, p.upper]);
              return [
                {
                  type: "line" as const,
                  shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] },
                  style: { stroke: blue, lineWidth: 1.5 },
                },
                ...[a, b].map((c) => ({
                  type: "line" as const,
                  shape: { x1: c[0] - 5, y1: c[1], x2: c[0] + 5, y2: c[1] },
                  style: { stroke: blue, lineWidth: 1.5 },
                })),
              ];
            }),
          };
        const segments: { point: ChartPoint; index: number }[][] = [];
        let active: { point: ChartPoint; index: number }[] = [];
        points.forEach((source, index) => {
          const point = secondary
            ? {
                ...source,
                lower: source.comparisonLower,
                upper: source.comparisonUpper,
              }
            : source;
          if (point.lower !== undefined && point.upper !== undefined)
            active.push({ point, index });
          else if (active.length) {
            segments.push(active);
            active = [];
          }
        });
        if (active.length) segments.push(active);
        return {
          type: "group",
          children: segments.map((segment) => ({
            type: "polygon" as const,
            shape: {
              points: [
                ...segment.map(({ point, index }) =>
                  api.coord([index, point.upper!]),
                ),
                ...segment
                  .map(({ point, index }) => api.coord([index, point.lower!]))
                  .reverse(),
              ],
            },
            style: { fill: secondary ? orange : blue, opacity: 0.14 },
          })),
        };
      };
    chart.setOption({
      animation: false,
      aria: { enabled: true, description: summary },
      grid: { top: 20, left: 58, right: 18, bottom: 42 },
      textStyle: { fontFamily: "Inter, sans-serif", color: muted },
      tooltip: { trigger: "axis", confine: true },
      xAxis: {
        type: "category",
        data: points.map((p) => p.period),
        boundaryGap: bar || coefficient,
        axisLabel: { color: muted, hideOverlap: true, fontSize: 10 },
        axisLine: { lineStyle: { color: border } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        scale: bar,
        min: scale.min,
        max: scale.max,
        interval: scale.step,
        axisLabel: {
          color: muted,
          fontSize: 10,
          formatter: (v: number) => tickLabel(v, scale.step),
        },
        splitLine: { lineStyle: { color: border, type: "dashed" } },
      },
      series: [
        ...(stack ?? []).map((s) => ({
          name: s.name,
          type: "bar",
          stack: "contributions",
          data: s.values,
          itemStyle: { color: s.color },
          barMaxWidth: 18,
        })),
        ...(points.some((p) => p.comparisonLower !== undefined)
          ? [
              {
                type: "custom",
                name: `${comparisonLabel} interval`,
                renderItem: renderBand(true),
                data: [0],
                silent: true,
                z: 0,
              },
            ]
          : []),
        ...(bands
          ? [
              {
                type: "custom",
                name: intervalLabel,
                renderItem: renderBand(),
                data: [0],
                silent: true,
                z: bar || coefficient ? 4 : 0,
              },
            ]
          : []),
        {
          name: title,
          type: coefficient ? "scatter" : bar ? "bar" : "line",
          data: points.map((p) => p.value),
          symbolSize: 8,
          showSymbol: coefficient,
          connectNulls: false,
          lineStyle: { width: 2.5, color: blue },
          itemStyle: { color: blue },
          barMaxWidth: 42,
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: muted, width: 1, type: "dashed" },
            data: [{ yAxis: 0 }],
          },
        },
        ...(points.some((p) => p.comparison !== undefined)
          ? [
              {
                name: comparisonLabel,
                type: "line",
                showSymbol: false,
                data: points.map((p) => p.comparison ?? null),
                lineStyle: { color: orange, type: "dashed", width: 2 },
              },
            ]
          : []),
      ],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [
    title,
    points,
    summary,
    bar,
    coefficient,
    comparisonLabel,
    axis,
    intervalLabel,
    stack,
  ]);
  return (
    <figure className="card chart-card" data-testid="result-chart">
      <figcaption>
        <span>{title}</span>
        <span className="muted mono">{unit}</span>
      </figcaption>
      <div
        className="chart-canvas"
        ref={element}
        role="img"
        aria-label={summary}
      />
      <p className="chart-summary">{summary}</p>
      {stack && (
        <p className="small">
          {stack.map((s) => (
            <span key={s.name} style={{ marginRight: 14 }}>
              <span style={{ color: s.color }}>■</span> {s.name}
            </span>
          ))}{" "}
          · Blue line: actual
        </p>
      )}
      {context && (
        <button
          className="link"
          aria-label={`Export PNG: ${title}`}
          onClick={() => {
            setExportError("");
            void exportPng(
              [
                {
                  name: title,
                  unit,
                  points,
                  summary,
                  bar,
                  coefficient,
                  axis,
                  intervalLabel,
                  stack,
                  pngNote,
                },
              ],
              { ...context, comparisonLabel },
            ).catch((e) => setExportError(String(e)));
          }}
        >
          Export PNG
        </button>
      )}
      {exportError && <p role="alert">{exportError}</p>}
      <details>
        <summary>Show chart data</summary>
        <DataTable rows={points.map((p) => ({ ...p }))} />
      </details>
    </figure>
  );
}
