/** Shared readable numeric scale for canvas exports and interactive charts. */
export interface AxisScale {
  min: number;
  max: number;
  step: number;
  ticks: number[];
}
export function niceScale(values: (number | null | undefined)[]): AxisScale {
  const finite = values.filter(
    (v): v is number => typeof v === "number" && Number.isFinite(v),
  );
  const low = Math.min(0, ...finite),
    high = Math.max(0, ...finite);
  const raw = (high - low || 1) / 5;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((v) => v * power >= raw) ?? 10) * power;
  const a = Math.floor(low / step),
    b = Math.ceil(high / step);
  const ticks = Array.from({ length: b - a + 1 }, (_, i) => (a + i) * step);
  if (ticks.length === 1) ticks.push(step);
  return { min: ticks[0], max: ticks[ticks.length - 1], step, ticks };
}
export function tickLabel(value: number, step: number): string {
  const digits = Math.min(20, Math.max(0, 1 - Math.floor(Math.log10(step))));
  return new Intl.NumberFormat("en", { maximumFractionDigits: digits }).format(
    Object.is(value, -0) ? 0 : value,
  );
}
