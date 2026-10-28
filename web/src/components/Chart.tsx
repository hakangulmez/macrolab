import { createPortal } from "react-dom";
import { usePrimaryChart } from "./PrimaryChart";
import { chartTheme, escapeHtml, useTheme } from "../theme";
import { useContext, useEffect, useRef, useState, type ReactNode } from "react";
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
import { LabelLayout } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";
import { niceScale, tickLabel, type AxisScale } from "../chartScale";
import { DataTable } from "./Common";
import { horizonAxisTitle } from "../format";
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
  LabelLayout,
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
  comparisonDisplayLabel = comparisonLabel,
  estimateLabel,
  comparisonShortLabel,
  displayTitle = title,
  displaySummary = summary,
  axis,
  intervalLabel = "Pointwise interval",
  exportContext,
  stack,
  pngNote,
  xAxisTitle,
  controls,
  primary = false,
  insight = false,
}: {
  controls?: ReactNode;
  primary?: boolean | number;
  insight?: boolean;
  title: string;
  unit: string;
  points: ChartPoint[];
  summary: string;
  first?: boolean;
  bar?: boolean;
  coefficient?: boolean;
  comparisonLabel?: string;
  comparisonDisplayLabel?: string;
  estimateLabel: string;
  comparisonShortLabel: string;
  displayTitle?: string;
  displaySummary?: string;
  axis?: AxisScale;
  intervalLabel?: string;
  exportContext?: PngContext;
  stack?: ResultChart["stack"];
  pngNote?: string;
  xAxisTitle?: string;
}) {
  const primaryTarget = usePrimaryChart(primary, insight);
  const theme = useTheme();
  const inherited = useContext(ChartExportContext);
  const context = exportContext ?? inherited;
  const xTitle =
    xAxisTitle ??
    (context?.horizon && !coefficient && typeof points[0]?.period === "number"
      ? horizonAxisTitle(context.frequency)
      : context?.forecast && !bar
        ? `Period (${context.frequency === "M" ? "months" : "quarters"})`
        : coefficient
          ? "Term"
          : bar
            ? "Category"
            : `Period (${context?.frequency === "M" ? "months" : context?.frequency === "Q" ? "quarters" : "time"})`);
  const [exportError, setExportError] = useState("");
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current || !points.length) return;
    const css = getComputedStyle(document.documentElement);
    const palette = chartTheme(theme);
    const blue = palette.color[0],
      orange = palette.color[1],
      muted = css.getPropertyValue("--muted").trim(),
      border = css.getPropertyValue("--border").trim();
    const chart = echarts.init(element.current, palette, {
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
      aria: { enabled: true, description: displaySummary },
      grid: {
        top: 25,
        left: 58,
        right:
          bar || coefficient
            ? 18
            : Math.max(
                75,
                Math.min(
                  145,
                  Math.max(estimateLabel.length, comparisonShortLabel.length) *
                    6 +
                    16,
                ),
              ),
        bottom: xTitle ? 58 : 42,
      },
      textStyle: { fontFamily: "Inter, sans-serif", color: muted },
      tooltip: {
        trigger: "axis",
        confine: true,
        axisPointer: { type: "cross", snap: true },
        formatter: (params: unknown) => {
          const rows = params as { dataIndex: number }[];
          const p = points[rows[0]?.dataIndex];
          if (!p) return "";
          const fmt = (v: unknown) =>
            typeof v === "number"
              ? new Intl.NumberFormat("en", {
                  maximumSignificantDigits: 4,
                  notation: "standard",
                }).format(v)
              : "—";
          return `<b>${escapeHtml(String(p.period))}</b><br><strong>${fmt(p.value)}</strong> ${escapeHtml(displayTitle)}<br>${escapeHtml(unit)}${p.lower !== undefined ? `<br>${fmt(p.lower)} – ${fmt(p.upper)} ${escapeHtml(intervalLabel)}` : ""}${p.comparison !== undefined ? `<br><strong>${fmt(p.comparison)}</strong> ${escapeHtml(comparisonShortLabel || comparisonDisplayLabel)}` : ""}${stack ? stack.map((s) => `<br><strong>${fmt(s.values[rows[0].dataIndex])}</strong> ${escapeHtml(s.name)}`).join("") : ""}`;
        },
      },
      xAxis: {
        name: xTitle,
        nameLocation: "middle",
        nameGap: 30,
        nameTextStyle: { color: muted, fontSize: 11 },
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
        ...(stack ?? []).map((s, index) => ({
          name: s.name,
          type: "bar",
          stack: "contributions",
          data: s.values,
          itemStyle: {
            color:
              stack!.length > 3
                ? index === 0
                  ? blue
                  : muted
                : palette.color[index % palette.color.length],
            opacity: stack!.length > 3 && index > 0 ? 0.55 : 1,
            borderWidth: 0.5,
            borderColor: palette.backgroundColor,
          },
          barMaxWidth: 18,
        })),
        ...(points.some((p) => p.comparisonLower !== undefined)
          ? [
              {
                type: "custom",
                name: `${comparisonDisplayLabel} interval`,
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
          name: estimateLabel,
          type: coefficient ? "scatter" : bar ? "bar" : "line",
          data: points.map((p) => p.value),
          symbolSize: 8,
          showSymbol: coefficient,
          connectNulls: false,
          lineStyle: { width: 2.5, color: blue },
          labelLayout: { moveOverlap: "shiftY" },
          endLabel: {
            show: !bar && !coefficient,
            formatter: () => (stack ? "Actual" : estimateLabel),
            color: muted,
            fontSize: 11,
          },
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
                name: comparisonShortLabel,
                type: "line",
                showSymbol: false,
                data: points.map((p) => p.comparison ?? null),
                lineStyle: { color: orange, type: "dashed", width: 2 },
                labelLayout: { moveOverlap: "shiftY" },
                endLabel: {
                  show: !bar && !coefficient,
                  formatter: () => comparisonShortLabel,
                  color: muted,
                  fontSize: 11,
                },
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
    theme,
    unit,
    title,
    points,
    summary,
    bar,
    coefficient,
    comparisonDisplayLabel,
    displayTitle,
    displaySummary,
    estimateLabel,
    comparisonShortLabel,
    axis,
    intervalLabel,
    stack,
    xTitle,
    primaryTarget,
  ]);
  const figure = (
    <figure className="card chart-card" data-testid="result-chart">
      {controls && <div className="row chart-controls">{controls}</div>}
      <figcaption>
        <span>{displayTitle}</span>
        <span className="muted mono">{unit}</span>
      </figcaption>
      <div
        className="chart-canvas"
        ref={element}
        role="img"
        aria-label={
          xTitle ? `${displaySummary} X-axis: ${xTitle}.` : displaySummary
        }
        data-x-axis-title={xTitle || undefined}
      />
      {!bar &&
        !coefficient &&
        !stack &&
        points.some((p) => p.comparison != null) && (
          <div className="legend" aria-label="Chart series">
            <span>
              <i className="legend-line" />
              {estimateLabel}
            </span>
            <span>
              <i className="legend-line comparison" />
              {comparisonShortLabel}
            </span>
          </div>
        )}
      <p className="chart-summary">{displaySummary}</p>
      {stack && (
        <p className="small">
          {stack.map((s, index) => (
            <span key={s.name} style={{ marginRight: 14 }}>
              <span
                style={{
                  color:
                    stack.length > 3
                      ? index === 0
                        ? chartTheme(theme).color[0]
                        : "var(--muted)"
                      : chartTheme(theme).color[index % 4],
                }}
              >
                ■
              </span>{" "}
              {s.name}
            </span>
          ))}{" "}
          · Blue line: actual
        </p>
      )}
      {context && (
        <button
          className="link"
          data-chart-export="png"
          aria-label={`Export PNG: ${displayTitle}`}
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
                  xAxisTitle,
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
      <details className="chart-values">
        <summary>Show chart data</summary>
        <DataTable rows={points.map((p) => ({ ...p }))} />
      </details>
    </figure>
  );
  return primaryTarget ? createPortal(figure, primaryTarget) : figure;
}
