import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  AriaComponent,
  MarkLineComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { applicationURL } from "../runtime";
import { chartTheme, escapeHtml, useTheme } from "../theme";
import { niceScale, tickLabel } from "../chartScale";
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  AriaComponent,
  MarkLineComponent,
  CanvasRenderer,
]);
interface Projection {
  snapshot_id: string;
  unit: string;
  countries: { iso3: string; name: string; values: [number, number][] }[];
}
export default function InflationHero({ snapshot }: { snapshot: string }) {
  const [data, setData] = useState<Projection | null>(null),
    [selected, setSelected] = useState("EA"),
    [error, setError] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  useEffect(() => {
    let active = true;
    void fetch(applicationURL("ui/inflation.json"))
      .then(async (r) => {
        if (!r.ok) throw Error("Snapshot chart is unavailable");
        const d = (await r.json()) as Projection;
        if (d.snapshot_id !== snapshot)
          throw Error("Chart and snapshot do not match");
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [snapshot]);
  useEffect(() => {
    if (!data || !ref.current) return;
    const colors = chartTheme(theme);
    const chart = echarts.init(ref.current, colors, { renderer: "canvas" });
    const years = [
      ...new Set(data.countries.flatMap((c) => c.values.map((v) => v[0]))),
    ].sort();
    const scale = niceScale(
      data.countries
        .filter((c) => c.iso3 !== "TUR")
        .flatMap((c) => c.values.map((v) => v[1])),
    );
    const focus = data.countries.find((c) => c.iso3 === selected)!;
    const lookup = new Map(
      data.countries.map((c) => [c.iso3, new Map(c.values)]),
    );
    const muted = theme === "dark" ? "#8E97A6" : "#5B6372";
    chart.setOption({
      animation: false,
      aria: {
        enabled: true,
        description:
          "Annual-average consumer-price inflation for all available economies. Türkiye is excluded only from the y-axis scaling.",
      },
      grid: { top: 30, left: 50, right: 90, bottom: 55 },
      tooltip: {
        trigger: "axis",
        confine: true,
        axisPointer: { type: "line", snap: true },
        formatter: (params: unknown) => {
          const entries = params as { dataIndex: number }[];
          const year = years[entries[0]?.dataIndex];
          const available = data.countries
            .flatMap((c) => {
              const v = lookup.get(c.iso3)?.get(year);
              return v === undefined ? [] : [v];
            })
            .sort((a, b) => a - b);
          const n = available.length;
          const median =
            n % 2
              ? available[(n - 1) / 2]
              : (available[n / 2 - 1] + available[n / 2]) / 2;
          const value = lookup.get(selected)?.get(year);
          const fmt = (v: number | undefined) =>
            v === undefined ? "Unavailable" : v.toFixed(2) + "%";
          return `<b>${year}</b><br><strong>${fmt(value)}</strong> ${escapeHtml(focus.name)}<br><strong>${fmt(median)}</strong> Median<br><strong>${fmt(available[0])} – ${fmt(available.at(-1))}</strong> Range<br>All ${n} available economies, including Türkiye and the euro-area aggregate.`;
        },
      },
      xAxis: {
        type: "category",
        data: years,
        name: "Year",
        nameLocation: "middle",
        nameGap: 30,
        axisLabel: { color: muted },
        axisLine: { lineStyle: { color: muted } },
        axisTick: { show: false },
      },
      yAxis: {
        min: scale.min,
        max: scale.max,
        interval: scale.step,
        name: "Inflation (%)",
        nameTextStyle: { color: muted },
        axisLabel: {
          color: muted,
          formatter: (v: number) => tickLabel(v, scale.step),
        },
        splitLine: {
          lineStyle: { color: theme === "dark" ? "#252C38" : "#E4E6ED" },
        },
      },
      series: [...data.countries.filter((c) => c.iso3 !== selected), focus].map(
        (c) => ({
          name: c.name,
          type: "line",
          clip: true,
          showSymbol: false,
          symbol: c.iso3 === selected ? "circle" : "none",
          symbolSize: 8,
          connectNulls: false,
          data: years.map((y) => lookup.get(c.iso3)?.get(y) ?? null),
          lineStyle: {
            width: c.iso3 === selected ? 2.8 : 1,
            color:
              c.iso3 === selected
                ? colors.color[0]
                : theme === "dark"
                  ? "#626C7E"
                  : "#A3AAB8",
            opacity: c.iso3 === selected ? 1 : 0.3,
          },
          itemStyle: { color: colors.color[0] },
          endLabel: {
            show: c.iso3 === selected,
            formatter: () => focus.name,
            color: muted,
            fontSize: 11,
          },
          emphasis: { disabled: true },
          markLine:
            c.iso3 === selected
              ? {
                  silent: true,
                  symbol: "none",
                  label: { show: false },
                  lineStyle: { color: muted, type: "dashed" },
                  data: [{ yAxis: 0 }],
                }
              : undefined,
        }),
      ),
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [data, selected, theme]);
  const latest = data?.countries
    .find((c) => c.iso3 === selected)
    ?.values.at(-1);
  return (
    <section
      className="inflation-hero card"
      aria-label="Inflation across economies"
    >
      <div className="row between">
        <div>
          <p className="overline">From the snapshot</p>
          <h2>One measure. Many economies.</h2>
        </div>
        {latest && (
          <div className="hero-latest">
            <strong className="mono">{latest[1].toFixed(2)}%</strong>
            <span>{latest[0]} annual average</span>
          </div>
        )}
      </div>
      <div className="hero-chips" aria-label="Highlight an economy">
        {[
          ["EA", "Euro area"],
          ["USA", "US"],
          ["JPN", "Japan"],
          ["GBR", "UK"],
          ["ESP", "Spain"],
        ].map(([iso, name]) => (
          <button
            key={iso}
            aria-pressed={selected === iso}
            onClick={() => setSelected(iso)}
          >
            {name}
          </button>
        ))}
      </div>
      <div
        className="hero-chart"
        ref={ref}
        data-testid="inflation-hero-chart"
        role="img"
        aria-label="Annual-average year-on-year consumer-price inflation, percent; x-axis: year"
      />
      {!data && <p role="status">{error || "Reading the snapshot chart…"}</p>}
      <p className="small muted">
        Annual mean of monthly y/y inflation · complete years only. Türkiye is
        excluded from axis scaling only; tooltip statistics include all
        available economies and the euro-area aggregate. Japan begins in{" "}
        {data?.countries.find((c) => c.iso3 === "JPN")?.values[0]?.[0] ??
          "its usable history"}
        .
      </p>
      <details>
        <summary>Chart values and scope</summary>
        <p className="small">
          Each year requires 12 observed monthly rates and their prior-year
          matches. No imputation or seasonal adjustment. Cross-country
          statistics describe the available economy aggregates, not a
          population-weighted statistic.
        </p>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Economy</th>
                <th>Year</th>
                <th>Annual-average inflation (%)</th>
              </tr>
            </thead>
            <tbody>
              {data?.countries
                .find((c) => c.iso3 === selected)
                ?.values.map(([y, v]) => (
                  <tr key={y}>
                    <td>
                      {data.countries.find((c) => c.iso3 === selected)?.name}
                    </td>
                    <td>{y}</td>
                    <td>{v.toFixed(3)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
