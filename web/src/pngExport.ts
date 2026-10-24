/** Self-contained raster exports from the same plotted points; no network or model work. */
import { download } from "./format";
import { buildVersion } from "./version";
import { niceScale, tickLabel } from "./chartScale";
import type { ResultChart } from "./resultData";

export interface PngContext {
  snapshot?: string;
  analysis: string;
  scenario?: string;
  country: string;
  sample: string;
  frequency: string;
  sources: string[];
  bandLevel: number;
  comparisonLabel: string;
  horizon: boolean;
  note?: string;
  intervalLabel?: string;
  estimateLabel?: string;
}
const blue = "#1D4ED8",
  orange = "#C2570C",
  ink = "#172033",
  muted = "#536075";

export function exportText(charts: ResultChart[], context: PngContext) {
  return {
    title: `${context.analysis} · ${context.country}`,
    sample: context.sample,
    legend: `${context.estimateLabel ?? "Estimate"} · ${context.intervalLabel ?? charts[0]?.intervalLabel ?? `${Math.round(context.bandLevel * 100)}% pointwise interval`}${charts.some((c) => !c.pngComparisonLabel && c.points.some((p) => p.comparison != null)) ? ` · ${context.comparisonLabel} (point estimate)` : ""}`,
    footer: `MacroLab ${buildVersion} · Data: ${context.sources.join(", ") || "see source cards"}${context.snapshot ? ` · Snapshot ${context.snapshot}` : ""} · Model scenario, not a forecast · hakangulmez.github.io/macrolab`,
  };
}

function wrapped(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  width: number,
  lineHeight: number,
) {
  let line = "";
  for (const word of text.split(/\s+/)) {
    if (line && ctx.measureText(`${line} ${word}`).width > width) {
      ctx.fillText(line, x, y);
      y += lineHeight;
      line = word;
    } else line = line ? `${line} ${word}` : word;
  }
  if (line) ctx.fillText(line, x, y);
  return y + lineHeight;
}

function plot(
  ctx: CanvasRenderingContext2D,
  chart: ResultChart,
  context: PngContext,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = ink;
  ctx.font = "600 18px Inter, sans-serif";
  let headerEnd = wrapped(ctx, chart.name, 24, 28, width - 48, 24);
  if (chart.transformation) {
    ctx.font = "14px Inter, sans-serif";
    ctx.fillStyle = muted;
    headerEnd = wrapped(
      ctx,
      chart.transformation,
      24,
      headerEnd + 3,
      width - 48,
      18,
    );
  }
  if (chart.pngNote) {
    ctx.font = "14px Inter, sans-serif";
    ctx.fillStyle = muted;
    headerEnd = wrapped(ctx, chart.pngNote, 24, headerEnd + 2, width - 48, 18);
  }
  if (
    chart.pngComparisonLabel &&
    chart.points.some((p) => p.comparison != null)
  ) {
    ctx.strokeStyle = orange;
    ctx.setLineDash([7, 5]);
    ctx.beginPath();
    ctx.moveTo(24, headerEnd + 6);
    ctx.lineTo(51, headerEnd + 6);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = ink;
    ctx.font = "14px Inter, sans-serif";
    headerEnd = wrapped(
      ctx,
      `${chart.pngComparisonLabel} · point estimate`,
      61,
      headerEnd + 11,
      width - 85,
      18,
    );
  }
  const coefficients = chart.coefficient === true;
  const left = coefficients ? Math.min(330, width * 0.4) : 90;
  const top = Math.max(86, headerEnd + 15),
    bottom = height - 85,
    right = width - 38;
  const values = chart.points
    .flatMap((p) => [
      p.value,
      p.lower,
      p.upper,
      p.comparison,
      p.comparisonLower,
      p.comparisonUpper,
    ])
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (chart.stack)
    chart.points.forEach((_, i) =>
      values.push(
        chart.stack!.reduce((s, c) => s + Math.max(0, c.values[i]), 0),
        chart.stack!.reduce((s, c) => s + Math.min(0, c.values[i]), 0),
      ),
    );
  const scale = chart.axis ?? niceScale(values);
  const { min, max } = scale;
  const valueX = (v: number) =>
    left + ((v - min) / (max - min)) * (right - left);
  const valueY = (v: number) =>
    bottom - ((v - min) / (max - min)) * (bottom - top);
  const periodX = (i: number) =>
    left +
    ((i + (chart.bar ? 0.5 : 0)) /
      Math.max(1, chart.points.length - (chart.bar ? 0 : 1))) *
      (right - left);
  const periodY = (i: number) =>
    top + ((i + 0.5) / chart.points.length) * (bottom - top);
  ctx.font = "13px Inter, sans-serif";
  for (const v of scale.ticks) {
    const tickX = coefficients ? valueX(v) : left;
    const tickY = coefficients ? bottom : valueY(v);
    ctx.strokeStyle = "#e2e7ef";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(coefficients ? tickX : left, coefficients ? top : tickY);
    ctx.lineTo(
      coefficients ? tickX : right,
      bottom === tickY ? bottom : coefficients ? bottom : tickY,
    );
    ctx.stroke();
    ctx.fillStyle = muted;
    ctx.textAlign = coefficients ? "center" : "right";
    ctx.fillText(
      tickLabel(v, scale.step),
      coefficients ? tickX : left - 12,
      coefficients ? bottom + 24 : tickY + 4,
    );
  }
  ctx.strokeStyle = muted;
  ctx.setLineDash([4, 5]);
  ctx.beginPath();
  ctx.moveTo(coefficients ? valueX(0) : left, coefficients ? top : valueY(0));
  ctx.lineTo(
    coefficients ? valueX(0) : right,
    coefficients ? bottom : valueY(0),
  );
  ctx.stroke();
  ctx.setLineDash([]);
  if (coefficients) {
    chart.points.forEach((point, i) => {
      const yy = periodY(i);
      ctx.fillStyle = ink;
      ctx.textAlign = "right";
      ctx.font = "13px Inter, sans-serif";
      const words = String(point.period);
      // Full labels are wrapped, never silently replaced by concept IDs or truncated.
      ctx.textAlign = "left";
      wrapped(ctx, words, 16, yy - 4, left - 30, 16);
      if (point.lower !== undefined && point.upper !== undefined) {
        ctx.strokeStyle = blue;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(valueX(point.lower), yy);
        ctx.lineTo(valueX(point.upper), yy);
        ctx.stroke();
        for (const value of [point.lower, point.upper]) {
          ctx.beginPath();
          ctx.moveTo(valueX(value), yy - 5);
          ctx.lineTo(valueX(value), yy + 5);
          ctx.stroke();
        }
      }
      if (point.value != null) {
        ctx.fillStyle = blue;
        ctx.beginPath();
        ctx.arc(valueX(point.value), yy, 5, 0, Math.PI * 2);
        ctx.fill();
      }
    });
  } else {
    if (chart.stack) {
      chart.points.forEach((_, i) => {
        let positive = 0,
          negative = 0;
        for (const s of chart.stack!) {
          const v = s.values[i],
            from = v >= 0 ? positive : negative;
          const to = from + v;
          ctx.fillStyle = s.color;
          ctx.fillRect(
            periodX(i) -
              Math.max(1, ((right - left) / chart.points.length) * 0.4),
            Math.min(valueY(from), valueY(to)),
            Math.max(2, ((right - left) / chart.points.length) * 0.8),
            Math.abs(valueY(to) - valueY(from)),
          );
          if (v >= 0) positive = to;
          else negative = to;
        }
      });
    }
    // A missing interval or estimate breaks a segment; exports never bridge a data gap.
    for (const secondary of [false, true]) {
      const lower = secondary ? "comparisonLower" : "lower",
        upper = secondary ? "comparisonUpper" : "upper";
      let segment: number[] = [];
      const band = () => {
        if (!segment.length) return;
        ctx.fillStyle = secondary
          ? "rgba(194,87,12,0.14)"
          : "rgba(29,78,216,0.14)";
        ctx.beginPath();
        segment.forEach((i, j) => {
          const p = chart.points[i];
          if (j) ctx.lineTo(periodX(i), valueY(p[upper]!));
          else ctx.moveTo(periodX(i), valueY(p[upper]!));
        });
        [...segment]
          .reverse()
          .forEach((i) =>
            ctx.lineTo(periodX(i), valueY(chart.points[i][lower]!)),
          );
        ctx.closePath();
        ctx.fill();
        segment = [];
      };
      chart.points.forEach((p, i) => {
        if (p[lower] !== undefined && p[upper] !== undefined) segment.push(i);
        else band();
      });
      band();
    }
    for (const field of ["value", "comparison"] as const) {
      ctx.strokeStyle = field === "value" ? blue : orange;
      ctx.fillStyle = blue;
      ctx.lineWidth = 2.5;
      ctx.setLineDash(field === "comparison" ? [7, 5] : []);
      ctx.beginPath();
      let active = false;
      chart.points.forEach((p, i) => {
        const v = p[field];
        if (v == null) {
          active = false;
          return;
        }
        if (chart.bar && field === "value") {
          const bw = Math.min(35, ((right - left) / chart.points.length) * 0.6);
          ctx.fillRect(
            periodX(i) - bw / 2,
            Math.min(valueY(v), valueY(0)),
            bw,
            Math.abs(valueY(v) - valueY(0)),
          );
        } else if (active) ctx.lineTo(periodX(i), valueY(v));
        else ctx.moveTo(periodX(i), valueY(v));
        active = true;
      });
      ctx.stroke();
      ctx.setLineDash([]);
    }
    const step = Math.max(1, Math.ceil(chart.points.length / 7));
    ctx.font = "12px Inter, sans-serif";
    ctx.fillStyle = muted;
    ctx.textAlign = "center";
    chart.points.forEach((p, i) => {
      if (i % step === 0 || i === chart.points.length - 1)
        ctx.fillText(String(p.period), periodX(i), bottom + 25);
    });
  }
  ctx.textAlign = "center";
  ctx.font = "14px Inter, sans-serif";
  ctx.fillStyle = ink;
  const timeUnit =
    context.frequency === "Q"
      ? "quarters"
      : context.frequency === "M"
        ? "months"
        : "years";
  wrapped(
    ctx,
    coefficients
      ? `Coefficient (${chart.unit})`
      : context.horizon
        ? `Horizon (${timeUnit} after the shock)`
        : `Period (${timeUnit})`,
    (left + right) / 2,
    height - 22,
    width - left - 30,
    19,
  );
  if (!coefficients) {
    ctx.save();
    ctx.translate(22, (top + bottom) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(chart.unit, 0, 0);
    ctx.restore();
  }
  ctx.restore();
}

export async function exportPng(
  charts: ResultChart[],
  context: PngContext,
): Promise<void> {
  if (!charts.length) throw new Error("No chart is available for export");
  await document.fonts.ready;
  const columns = charts.length > 1 ? 2 : 1,
    width = columns === 2 ? 1760 : 1200;
  const cellWidth = (width - 48) / columns;
  const cellHeight = Math.max(
    520,
    ...charts
      .filter((c) => c.coefficient)
      .map((c) => c.points.length * 50 + 180),
  );
  const height = 230 + Math.ceil(charts.length / columns) * cellHeight + 100;
  const canvas = document.createElement("canvas");
  canvas.width = width * 2;
  canvas.height = height * 2;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("PNG canvas is unavailable");
  ctx.scale(2, 2);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  const text = exportText(charts, context);
  ctx.fillStyle = ink;
  ctx.font = "600 26px Inter, sans-serif";
  const titleEnd = wrapped(ctx, text.title, 40, 45, width - 80, 32);
  ctx.font = "15px Inter, sans-serif";
  ctx.fillStyle = muted;
  wrapped(ctx, text.sample, 40, titleEnd + 8, width - 80, 18);
  if (context.scenario) ctx.fillText(context.scenario, 40, titleEnd + 33);
  const legendY = titleEnd + 67;
  ctx.strokeStyle = blue;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(40, legendY - 5);
  ctx.lineTo(65, legendY - 5);
  ctx.stroke();
  ctx.fillStyle = ink;
  ctx.fillText(context.estimateLabel ?? "Estimate", 75, legendY);
  if (charts.every((c) => c.coefficient)) {
    ctx.fillStyle = blue;
    ctx.beginPath();
    ctx.arc(52, legendY - 5, 5, 0, Math.PI * 2);
    ctx.fill();
  }
  const hasBands = charts.some((c) =>
    c.points.some((p) => p.lower !== undefined),
  );
  if (hasBands) {
    ctx.fillStyle = "rgba(29,78,216,.14)";
    if (charts.every((c) => c.coefficient)) {
      ctx.strokeStyle = blue;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(175, legendY - 7);
      ctx.lineTo(201, legendY - 7);
      for (const x of [175, 201]) {
        ctx.moveTo(x, legendY - 13);
        ctx.lineTo(x, legendY - 1);
      }
      ctx.stroke();
    } else ctx.fillRect(175, legendY - 16, 26, 17);
    ctx.fillStyle = ink;
    ctx.fillText(
      context.intervalLabel ??
        charts[0]?.intervalLabel ??
        `${Math.round(context.bandLevel * 100)}% pointwise interval`,
      212,
      legendY,
    );
  }
  if (
    charts.some(
      (c) =>
        !c.pngComparisonLabel && c.points.some((p) => p.comparison != null),
    )
  ) {
    ctx.strokeStyle = orange;
    ctx.setLineDash([7, 5]);
    ctx.beginPath();
    ctx.moveTo(450, legendY - 5);
    ctx.lineTo(477, legendY - 5);
    ctx.stroke();
    ctx.setLineDash([]);
    wrapped(
      ctx,
      `${context.comparisonLabel}${charts.some((c) => c.points.some((p) => p.comparisonLower !== undefined)) ? " · 68% pointwise band" : " · point estimate"}`,
      489,
      legendY,
      width - 530,
      20,
    );
  }
  if (context.note) {
    ctx.fillStyle = muted;
    ctx.font = "14px Inter, sans-serif";
    wrapped(ctx, context.note, 40, 191, width - 80, 18);
  }
  if (charts[0]?.stack) {
    ctx.fillStyle = ink;
    ctx.font = "14px Inter, sans-serif";
    wrapped(
      ctx,
      charts[0].stack.map((s) => s.name).join(" · ") + " · Actual: blue line",
      40,
      191,
      width - 80,
      18,
    );
  }
  charts.forEach((chart, i) =>
    plot(
      ctx,
      chart,
      context,
      24 + (i % columns) * cellWidth,
      230 + Math.floor(i / columns) * cellHeight,
      cellWidth,
      cellHeight,
    ),
  );
  ctx.fillStyle = muted;
  ctx.font = "14px Inter, sans-serif";
  ctx.textAlign = "left";
  wrapped(ctx, text.footer, 40, height - 55, width - 80, 22);
  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("PNG encoding failed"))),
      "image/png",
    ),
  );
  download(
    blob,
    charts.length > 1 ? "macrolab-response-panel.png" : "macrolab-chart.png",
  );
}
