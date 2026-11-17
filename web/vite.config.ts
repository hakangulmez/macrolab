import react from "@vitejs/plugin-react";
import type { ProxyOptions } from "vite";
import { defineConfig } from "vitest/config";

const base = process.env.MACROLAB_BASE_PATH ?? "/";
if (!/^\/(?:[A-Za-z0-9_-]+\/)*$/.test(base)) {
  throw new Error(
    "MACROLAB_BASE_PATH must be an absolute directory path with a trailing slash.",
  );
}

const reportsPath =
  process.env.MACROLAB_REPORTS_LOCAL === "1" ? `${base}api/reports/ask` : "";
const reportsProxy: Record<string, ProxyOptions> | undefined = reportsPath
  ? Object.fromEntries(
      [
        [reportsPath, "/ask", "POST"],
        [reportsPath.replace(/\/ask$/, "/reports"), "/reports", "GET"],
      ].map(([path, targetPath, method]) => [
        `^${path}$`,
        {
          target: "http://127.0.0.1:18082",
          changeOrigin: true,
          rewrite: () => targetPath,
          bypass(req) {
            if (
              req.method !== method ||
              (req.headers.origin &&
                req.headers.origin !== `http://${req.headers.host}`)
            ) {
              return false;
            }
          },
          configure(proxy) {
            // The incoming origin was checked before forwarding to the local service.
            proxy.on("proxyReq", (req) => req.removeHeader("origin"));
          },
        } satisfies ProxyOptions,
      ]),
    )
  : undefined;

export default defineConfig({
  base,
  define: {
    "import.meta.env.MACROLAB_REPORTS_PATH": JSON.stringify(reportsPath),
    "import.meta.env.MACROLAB_TIMELINE_ENABLED":
      process.env.MACROLAB_TIMELINE_ENABLED !== "0",
  },
  publicDir: process.env.MACROLAB_PUBLIC_DIR ?? "public",
  build: {
    outDir: process.env.MACROLAB_BUILD_DIR ?? "dist",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/zrender/")) return "chart-renderer";
          if (id.includes("/echarts/lib/chart/")) return "chart-series";
          if (id.includes("/echarts/lib/component/")) return "chart-components";
          if (id.includes("/echarts/")) return "chart-core";
        },
      },
    },
  },
  plugins: [react()],
  server: { host: "127.0.0.1", proxy: reportsProxy },
  preview: { host: "127.0.0.1", proxy: reportsProxy },
  test: {
    environment: "node",
    include: ["tests/**/*.test.{ts,tsx}"],
    passWithNoTests: false,
  },
});
