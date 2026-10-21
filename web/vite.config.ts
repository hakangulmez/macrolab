import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const base = process.env.MACROLAB_BASE_PATH ?? "/";
if (!/^\/(?:[A-Za-z0-9_-]+\/)*$/.test(base)) {
  throw new Error(
    "MACROLAB_BASE_PATH must be an absolute directory path with a trailing slash.",
  );
}

export default defineConfig({
  base,
  publicDir: process.env.MACROLAB_PUBLIC_DIR ?? "public",
  build: { outDir: process.env.MACROLAB_BUILD_DIR ?? "dist" },
  plugins: [react()],
  server: { host: "127.0.0.1" },
  preview: { host: "127.0.0.1" },
  test: {
    environment: "node",
    include: ["tests/**/*.test.{ts,tsx}"],
    passWithNoTests: false,
  },
});
