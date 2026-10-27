import type { EChartsType } from "echarts/core";

// Accepted v2.3.0 plot sizes in CSS pixels; exports always use a 2x raster.
// Titles, legends, notes and the footer are added by the existing serializer.
export function canonicalChartImage(
  chart: Pick<EChartsType, "getWidth" | "getHeight" | "resize" | "getDataURL">,
  width: 966 | 916,
  backgroundColor: string,
): string {
  const screen = { width: chart.getWidth(), height: chart.getHeight() };
  try {
    chart.resize({ width, height: 340, silent: true });
    return chart.getDataURL({ pixelRatio: 2, backgroundColor });
  } finally {
    chart.resize({ ...screen, silent: true });
  }
}
