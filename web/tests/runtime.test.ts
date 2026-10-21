import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AnalysisConfig } from "../src/types";
import type { AnalysisBundle } from "../src/runtime";

interface Request {
  id: number;
  type: string;
  indexURL?: string;
  wheelURL?: string;
}
class ControlledWorker {
  static instances: ControlledWorker[] = [];
  static autoInitialize = true;
  onmessage?: (event: MessageEvent) => void;
  onerror?: (event: ErrorEvent) => void;
  requests: Request[] = [];
  terminated = false;
  url: string;
  constructor(url: URL) {
    this.url = url.href;
    ControlledWorker.instances.push(this);
  }
  postMessage(message: Request) {
    this.requests.push(message);
    if (message.type === "init" && ControlledWorker.autoInitialize)
      queueMicrotask(() => this.reply(message.id, {}));
  }
  reply(id: number, result: unknown) {
    this.onmessage?.({ data: { id, type: "result", result } } as MessageEvent);
  }
  terminate() {
    this.terminated = true;
  }
}
const config = {
  countries: ["USA"],
  series: [],
  snapshot_id: "test",
} as unknown as AnalysisConfig;
const bundle: AnalysisBundle = {
  schema_version: 1,
  snapshot_id: "test",
  as_of_date: "2026-10-21",
  countries: {},
};

beforeEach(() => {
  vi.resetModules();
  ControlledWorker.instances = [];
  ControlledWorker.autoInitialize = true;
  vi.stubGlobal("Worker", ControlledWorker);
  vi.stubGlobal("location", {
    href: "http://127.0.0.1:5173/",
    origin: "http://127.0.0.1:5173",
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            snapshot_id: "test",
            countries: [],
            publication_approved: false,
            runtime: {
              worker_url: "/runtime/worker.mjs",
              index_url: "/runtime/pyodide/",
              wheel_url: "/runtime/source.whl",
              wheel_sha256: "test",
              code_version: "test",
            },
          }),
        ),
    ),
  );
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("worker lifecycle", () => {
  it("initializes all scientific assets under a static project subpath", async () => {
    vi.stubEnv("BASE_URL", "/macrolab/");
    const { AnalysisRuntime } = await import("../src/runtime");
    const runtime = new AnalysisRuntime();
    await runtime.prewarm();
    const worker = ControlledWorker.instances[0];
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe(
      "http://127.0.0.1:5173/macrolab/data/manifest.json",
    );
    expect(worker.url).toBe(
      "http://127.0.0.1:5173/macrolab/runtime/worker.mjs",
    );
    expect(worker.requests[0].indexURL).toBe(
      "http://127.0.0.1:5173/macrolab/runtime/pyodide/",
    );
    expect(worker.requests[0].wheelURL).toBe(
      "http://127.0.0.1:5173/macrolab/runtime/source.whl",
    );
    runtime.dispose();
  });
  it("keeps background progress quiet and reports progress after an interactive operation joins", async () => {
    const { AnalysisRuntime } = await import("../src/runtime");
    const progress = vi.fn();
    const runtime = new AnalysisRuntime(progress);
    await runtime.prewarm();
    const worker = ControlledWorker.instances[0];
    worker.onmessage?.({
      data: { type: "progress", text: "background" },
    } as MessageEvent);
    expect(progress).not.toHaveBeenCalled();
    const run = runtime.run(config, bundle);
    await vi.waitFor(() => expect(worker.requests).toHaveLength(2));
    worker.onmessage?.({
      data: { type: "progress", text: "interactive" },
    } as MessageEvent);
    expect(progress).toHaveBeenCalledExactlyOnceWith("interactive");
    worker.reply(worker.requests[1].id, { status: "ok" });
    await run;
    runtime.dispose();
  });
  it("shares a background warm-up with a run started before initialization finishes", async () => {
    ControlledWorker.autoInitialize = false;
    const { AnalysisRuntime } = await import("../src/runtime");
    const runtime = new AnalysisRuntime();
    const warmup = runtime.prewarm();
    const secondWarmup = runtime.prewarm();
    const run = runtime.run(config, bundle);
    expect(secondWarmup).toBe(warmup);
    await vi.waitFor(() =>
      expect(ControlledWorker.instances[0]?.requests).toHaveLength(1),
    );
    const worker = ControlledWorker.instances[0];
    expect(worker.requests.map((request) => request.type)).toEqual(["init"]);
    worker.reply(worker.requests[0].id, {});
    await warmup;
    await vi.waitFor(() => expect(worker.requests).toHaveLength(2));
    expect(ControlledWorker.instances).toHaveLength(1);
    worker.reply(worker.requests[1].id, { status: "ok" });
    await expect(run).resolves.toEqual({ status: "ok" });
    runtime.dispose();
  });

  it("rejects cancelled warm-up and recovers on the next run without reusing a terminated worker", async () => {
    ControlledWorker.autoInitialize = false;
    const { AnalysisRuntime } = await import("../src/runtime");
    const runtime = new AnalysisRuntime();
    const warmup = runtime.prewarm();
    const rejected = expect(warmup).rejects.toThrow("Cancelled");
    await vi.waitFor(() =>
      expect(ControlledWorker.instances[0]?.requests).toHaveLength(1),
    );
    const previous = ControlledWorker.instances[0];
    runtime.cancel();
    await rejected;
    expect(previous.terminated).toBe(true);
    ControlledWorker.autoInitialize = true;
    const run = runtime.run(config, bundle);
    await vi.waitFor(() =>
      expect(ControlledWorker.instances[1]?.requests).toHaveLength(2),
    );
    const worker = ControlledWorker.instances[1];
    previous.reply(previous.requests[0].id, {});
    worker.reply(worker.requests[1].id, { status: "ok" });
    await expect(run).resolves.toEqual({ status: "ok" });
    runtime.dispose();
  });

  it("surfaces initialization failure and retries with a fresh worker", async () => {
    ControlledWorker.autoInitialize = false;
    const { AnalysisRuntime } = await import("../src/runtime");
    const runtime = new AnalysisRuntime();
    const warmup = runtime.prewarm();
    const rejected = expect(warmup).rejects.toThrow("local asset missing");
    await vi.waitFor(() =>
      expect(ControlledWorker.instances[0]?.requests).toHaveLength(1),
    );
    const previous = ControlledWorker.instances[0];
    previous.onerror?.({ message: "local asset missing" } as ErrorEvent);
    await rejected;
    expect(previous.terminated).toBe(true);
    ControlledWorker.autoInitialize = true;
    await runtime.prewarm();
    expect(ControlledWorker.instances).toHaveLength(2);
    expect(ControlledWorker.instances[1].terminated).toBe(false);
    runtime.dispose();
  });

  it("serializes operations instead of sending a second calculation while one is busy", async () => {
    const { AnalysisRuntime } = await import("../src/runtime");
    const runtime = new AnalysisRuntime();
    const first = runtime.run(config, bundle);
    const second = runtime.compatibility(config, bundle);
    await vi.waitFor(() =>
      expect(ControlledWorker.instances[0]?.requests).toHaveLength(2),
    );
    const worker = ControlledWorker.instances[0];
    expect(worker.requests.map((item) => item.type)).toEqual(["init", "run"]);
    worker.reply(worker.requests[1].id, { status: "ok" });
    await expect(first).resolves.toEqual({ status: "ok" });
    await vi.waitFor(() => expect(worker.requests).toHaveLength(3));
    worker.reply(worker.requests[2].id, { models: [] });
    await expect(second).resolves.toEqual({ models: [] });
    runtime.dispose();
  });

  it("cancels without a partial result and ignores errors from the terminated generation", async () => {
    const { AnalysisRuntime } = await import("../src/runtime");
    const runtime = new AnalysisRuntime();
    const cancelled = runtime.run(config, bundle);
    const rejected = expect(cancelled).rejects.toThrow("Cancelled");
    await vi.waitFor(() =>
      expect(ControlledWorker.instances[0]?.requests).toHaveLength(2),
    );
    const previous = ControlledWorker.instances[0];
    runtime.cancel();
    await rejected;
    expect(previous.terminated).toBe(true);
    const restarted = runtime.run(config, bundle);
    await vi.waitFor(() =>
      expect(ControlledWorker.instances[1]?.requests).toHaveLength(2),
    );
    const current = ControlledWorker.instances[1];
    previous.onerror?.({ message: "late old-worker failure" } as ErrorEvent);
    previous.reply(previous.requests[1].id, { status: "old result" });
    expect(current.terminated).toBe(false);
    current.reply(current.requests[1].id, { status: "ok", generation: 2 });
    await expect(restarted).resolves.toEqual({ status: "ok", generation: 2 });
    runtime.dispose();
  });
});
