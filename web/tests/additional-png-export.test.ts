import { expect, it, vi } from "vitest";
import { canonicalChartImage } from "../src/additionalPngExport";

it.each([966, 916] as const)(
  "exports at canonical width %i independently of the responsive container",
  (width) => {
    for (const screenWidth of [275, 1260]) {
      let size = { width: screenWidth, height: 340 };
      const chart = {
        getWidth: () => size.width,
        getHeight: () => size.height,
        resize: vi.fn((next) => {
          size = next;
        }),
        getDataURL: vi.fn((options) => JSON.stringify({ size, options })),
      };
      const png = JSON.parse(canonicalChartImage(chart, width, "#ffffff"));
      expect(png.size).toEqual({ width, height: 340, silent: true });
      expect(png.options).toEqual({
        pixelRatio: 2,
        backgroundColor: "#ffffff",
      });
      expect(chart.getWidth()).toBe(screenWidth);
      expect(chart.getHeight()).toBe(340);
    }
  },
);

it("restores the screen geometry when PNG rendering fails", () => {
  let size = { width: 275, height: 340 };
  const chart = {
    getWidth: () => size.width,
    getHeight: () => size.height,
    resize: vi.fn((next) => {
      size = next;
    }),
    getDataURL: () => {
      throw new Error("Canvas unavailable");
    },
  };
  expect(() => canonicalChartImage(chart, 966, "#ffffff")).toThrow(
    "Canvas unavailable",
  );
  expect(chart.getWidth()).toBe(275);
  expect(chart.getHeight()).toBe(340);
});
