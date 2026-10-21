import type { AnalysisConfig } from "./types";

type JsonRecord = Record<string, unknown>;
export interface RuntimeMetadata {
  worker_url: string;
  index_url: string;
  wheel_url: string;
  wheel_sha256: string;
  code_version: string;
  source_archive_sha256: string;
  asset_lock_url: string;
  capabilities: string[];
  reproduction_environment: {
    python_version: string;
    dependencies: Record<string, string>;
  };
}
export interface DataManifest extends JsonRecord {
  snapshot_id: string;
  as_of_date: string;
  publication_approved: false;
  countries: JsonRecord[];
  indicators: JsonRecord[];
  models: JsonRecord[];
  templates: {
    id: string;
    title: string;
    description: string;
    config: AnalysisConfig;
  }[];
  validation: { gate: string; code_version: string; models: JsonRecord[] };
  sources: JsonRecord[];
  coverage_summary: JsonRecord;
  coverage: (JsonRecord & {
    country: string;
    concept_id: string;
    status: string;
    first_date: string | null;
    last_date: string | null;
    reason_codes: string[];
    stale: boolean;
  })[];
  national_concepts: number;
  global_factors: number;
  country_files: Record<string, { url: string; sha256: string; bytes: number }>;
  schema_url: string;
  global_variants_url: string;
  runtime: RuntimeMetadata;
}
export interface CountryBundle extends JsonRecord {
  snapshot_id: string;
  as_of_date: string;
  country: JsonRecord & { iso3: string };
  cards: (JsonRecord & { concept_id: string })[];
  profiles: JsonRecord[];
  series: Record<string, [string, number][]>;
  publication_approved: false;
}
export interface AnalysisBundle {
  schema_version: number;
  snapshot_id: string;
  as_of_date: string;
  countries: Record<
    string,
    {
      metadata: JsonRecord;
      series: Record<
        string,
        { metadata: JsonRecord; observations: [string, number][] }
      >;
    }
  >;
}

let manifestPromise: Promise<DataManifest> | undefined;
const countries = new Map<string, Promise<CountryBundle>>();

export function applicationURL(
  path: string,
  base = import.meta.env.BASE_URL,
): URL {
  const root = new URL(base, location.origin);
  let url: URL;
  if (/^[a-z][a-z\d+.-]*:/i.test(path) || path.startsWith("//")) {
    url = new URL(path, root);
  } else if (root.pathname !== "/" && path.startsWith(root.pathname)) {
    url = new URL(path, location.origin);
  } else {
    // Snapshot manifests use both app-relative and legacy leading-slash paths.
    url = new URL(path.replace(/^\//, ""), root);
  }
  if (
    url.origin !== location.origin ||
    !url.pathname.startsWith(root.pathname)
  ) {
    throw new Error("Only assets within this application can be loaded.");
  }
  return url;
}

async function localResponse(path: string): Promise<Response> {
  const url = applicationURL(path);
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok)
    throw new Error(
      `Local data is unavailable (${response.status}). Run the local data preparation step.`,
    );
  return response;
}

export function getManifest(): Promise<DataManifest> {
  manifestPromise ??= localResponse("/data/manifest.json")
    .then(async (response) => {
      const data = (await response.json()) as DataManifest;
      if (
        !data.snapshot_id ||
        !Array.isArray(data.countries) ||
        data.publication_approved !== false
      ) {
        throw new Error("The local data manifest is invalid.");
      }
      return data;
    })
    .catch((error: unknown) => {
      manifestPromise = undefined;
      throw error;
    });
  return manifestPromise;
}

export async function getCountry(iso3: string): Promise<CountryBundle> {
  const manifest = await getManifest();
  const file = manifest.country_files[iso3];
  if (!file) throw new Error(`Country ${iso3} is outside this data snapshot.`);
  const key = `${manifest.snapshot_id}/${iso3}`;
  if (!countries.has(key)) {
    countries.set(
      key,
      (async () => {
        const raw = await (await localResponse(file.url)).arrayBuffer();
        const hash = Array.from(
          new Uint8Array(await crypto.subtle.digest("SHA-256", raw)),
        )
          .map((byte) => byte.toString(16).padStart(2, "0"))
          .join("");
        if (raw.byteLength !== file.bytes || hash !== file.sha256)
          throw new Error(
            "Country data checksum differs from the accepted snapshot.",
          );
        const bundle = JSON.parse(
          new TextDecoder().decode(raw),
        ) as CountryBundle;
        if (
          bundle.country.iso3 !== iso3 ||
          bundle.snapshot_id !== manifest.snapshot_id
        )
          throw new Error("Country data belongs to a different snapshot.");
        return bundle;
      })().catch((error: unknown) => {
        countries.delete(key);
        throw error;
      }),
    );
  }
  return countries.get(key)!;
}

export async function buildBundle(
  config: AnalysisConfig,
): Promise<AnalysisBundle> {
  const manifest = await getManifest();
  if (config.snapshot_id !== manifest.snapshot_id)
    throw new Error(
      "This configuration requests a snapshot that is not installed locally.",
    );
  const selected = await Promise.all(config.countries.map(getCountry));
  const concepts = new Set(config.series.map((series) => series.concept_id));
  if (
    config.comparison?.enabled !== false &&
    config.comparison?.scenarios?.includes("extended_var")
  ) {
    concepts.add("reer");
    concepts.add("credit_pnfs");
  }
  const bundle: AnalysisBundle = {
    schema_version: 1,
    snapshot_id: manifest.snapshot_id,
    as_of_date: manifest.as_of_date,
    countries: {},
  };
  for (const country of selected) {
    const cards = new Map(country.cards.map((card) => [card.concept_id, card]));
    bundle.countries[country.country.iso3] = {
      metadata: country.country,
      series: Object.fromEntries(
        [...concepts].map((concept) => [
          concept,
          {
            metadata: cards.get(concept) ?? {
              concept_id: concept,
              status: "missing",
            },
            observations: country.series[concept] ?? [],
          },
        ]),
      ),
    };
  }
  return bundle;
}

export class AnalysisRuntime {
  private worker?: Worker;
  private ready?: Promise<void>;
  private sequence = 0;
  private generation = 0;
  private activeOperation = false;
  private pending = new Map<
    number,
    { resolve: (result: unknown) => void; reject: (error: Error) => void }
  >();
  private queue: Promise<unknown> = Promise.resolve();
  constructor(
    private readonly onProgress: (text: string) => void = () => undefined,
  ) {}

  private reset(error: Error): void {
    this.generation += 1;
    this.worker?.terminate();
    this.worker = undefined;
    this.ready = undefined;
    for (const promise of this.pending.values()) promise.reject(error);
    this.pending.clear();
    this.queue = Promise.resolve();
    this.activeOperation = false;
  }

  private progress(message: string): void {
    // A background warm-up has no interactive progress UI. Joining operations
    // still receive subsequent initialization and calculation updates.
    if (this.activeOperation) this.onProgress(message);
  }

  private request(message: JsonRecord): Promise<unknown> {
    const worker = this.worker;
    if (!worker)
      return Promise.reject(new Error("The analysis runtime is unavailable."));
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      this.pending.set(id, { resolve, reject });
      try {
        worker.postMessage({ id, ...message });
      } catch (error) {
        this.pending.delete(id);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private initialise(): Promise<void> {
    if (!this.ready) {
      const generation = this.generation;
      this.ready = (async () => {
        this.progress("Preparing the local analysis runtime…");
        const manifest = await getManifest();
        if (generation !== this.generation) throw new Error("Cancelled");
        const workerURL = applicationURL(manifest.runtime.worker_url);
        this.worker = new Worker(workerURL, { type: "module" });
        this.worker.onmessage = ({
          data,
        }: MessageEvent<{
          id?: number;
          type: string;
          text?: string;
          result?: unknown;
          message?: string;
        }>) => {
          if (generation !== this.generation) return;
          if (data.type === "progress") {
            this.progress(data.text ?? "Working…");
            return;
          }
          if (data.type === "log") return;
          const pending =
            data.id === undefined ? undefined : this.pending.get(data.id);
          if (!pending || data.id === undefined) return;
          this.pending.delete(data.id);
          if (data.type === "error")
            pending.reject(new Error(data.message ?? "Analysis failed."));
          else pending.resolve(data.result);
        };
        this.worker.onerror = (event) => {
          if (generation !== this.generation) return;
          this.reset(
            new Error(
              event.message || "The analysis worker stopped unexpectedly.",
            ),
          );
        };
        await this.request({
          type: "init",
          indexURL: applicationURL(manifest.runtime.index_url).href,
          wheelURL: applicationURL(manifest.runtime.wheel_url).href,
          wheelSHA256: manifest.runtime.wheel_sha256,
          codeVersion: manifest.runtime.code_version,
          reproductionEnvironment: manifest.runtime.reproduction_environment,
        });
      })().catch((error: unknown) => {
        if (generation === this.generation)
          this.reset(error instanceof Error ? error : new Error(String(error)));
        throw error;
      });
    }
    return this.ready;
  }

  private async operation<T>(message: JsonRecord): Promise<T> {
    const generation = this.generation;
    const operation = this.queue
      .catch(() => undefined)
      .then(async () => {
        if (generation !== this.generation) throw new Error("Cancelled");
        this.activeOperation = true;
        try {
          await this.initialise();
          if (generation !== this.generation) throw new Error("Cancelled");
          return (await this.request(message)) as T;
        } finally {
          if (generation === this.generation) this.activeOperation = false;
        }
      });
    this.queue = operation.catch(() => undefined);
    return operation;
  }

  prewarm(): Promise<void> {
    return this.initialise();
  }

  run(config: AnalysisConfig, bundle: AnalysisBundle): Promise<JsonRecord> {
    return this.operation({ type: "run", config, bundle });
  }
  compatibility(
    config: AnalysisConfig,
    bundle: AnalysisBundle,
  ): Promise<JsonRecord> {
    return this.operation({ type: "compatibility", config, bundle });
  }
  encode(config: AnalysisConfig): Promise<string> {
    return this.operation({ type: "encode", config });
  }
  decode(token: string): Promise<AnalysisConfig> {
    return this.operation({ type: "decode", token });
  }
  exportPython(
    config: AnalysisConfig,
    bundle: AnalysisBundle,
  ): Promise<string> {
    return this.operation({ type: "export", config, bundle });
  }
  cancel(): void {
    this.reset(new Error("Cancelled"));
    this.onProgress("Cancelled. Ready for a new analysis.");
  }
  dispose(): void {
    this.reset(new Error("Runtime closed"));
  }
}
