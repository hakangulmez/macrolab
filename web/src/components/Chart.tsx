import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import {
  LineChart,
  BarChart,
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
import { download, number } from "../format";
import { DataTable } from "./Common";
echarts.use([
  LineChart,
  BarChart,
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
}
export function Chart({
  title,
  unit,
  points,
  summary,
  first = false,
  bar = false,
  comparisonLabel = "Comparison",
}: {
  title: string;
  unit: string;
  points: ChartPoint[];
  summary: string;
  first?: boolean;
  bar?: boolean;
  comparisonLabel?: string;
}) {
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
      .flatMap((p) => [p.value, p.lower, p.upper, p.comparison])
      .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    const low = Math.min(0, ...extent),
      high = Math.max(0, ...extent);
    const padding = (high - low || 1) * 0.08;
    const render: NonNullable<CustomSeriesOption["renderItem"]> = (
      _params,
      api,
    ) => {
      if (bar)
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
      points.forEach((point, index) => {
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
          style: { fill: blue, opacity: 0.14 },
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
        boundaryGap: bar,
        axisLabel: { color: muted, hideOverlap: true, fontSize: 10 },
        axisLine: { lineStyle: { color: border } },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        scale: bar,
        min: low - padding,
        max: high + padding,
        axisLabel: {
          color: muted,
          fontSize: 10,
          formatter: (v: number) => number(v, 2),
        },
        splitLine: { lineStyle: { color: border, type: "dashed" } },
      },
      series: [
        ...(bands
          ? [
              {
                type: "custom",
                name: "Pointwise interval",
                renderItem: render,
                data: [0],
                silent: true,
                z: bar ? 4 : 0,
              },
            ]
          : []),
        {
          name: title,
          type: bar ? "bar" : "line",
          data: points.map((p) => p.value),
          showSymbol: false,
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
    const exportPNG = () => {
      if (!first) return;
      const url = chart.getDataURL({
        type: "png",
        pixelRatio: 2,
        backgroundColor: css.getPropertyValue("--surface").trim(),
      });
      fetch(url)
        .then((r) => r.blob())
        .then((blob) => download(blob, "macrolab-chart.png"));
    };
    window.addEventListener("macrolab-export-png", exportPNG);
    return () => {
      observer.disconnect();
      window.removeEventListener("macrolab-export-png", exportPNG);
      chart.dispose();
    };
  }, [title, points, summary, first, bar, comparisonLabel]);
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
      <details>
        <summary>Show chart data</summary>
        <DataTable rows={points.map((p) => ({ ...p }))} />
      </details>
    </figure>
  );
}
