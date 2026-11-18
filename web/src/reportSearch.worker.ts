import { gunzipSync, strFromU8 } from "fflate";
import manifest from "./data/report-search/manifest.json";
import {
  EvidenceIndex,
  planEvidenceSearch,
  type EvidenceFilters,
  type EvidencePassage,
} from "./reportSearch";

const urls = import.meta.glob("./data/report-search/*.gz", {
  query: "?url",
  import: "default",
  eager: true,
}) as Record<string, string>;
const index = new EvidenceIndex();
const loaded = new Set<string>();
let queue: Promise<unknown> = Promise.resolve();
async function load(key: string) {
  if (loaded.has(key)) return;
  const shard = manifest.shards.find((s) => s.key === key);
  if (!shard) return;
  const url = urls[`./data/report-search/${shard.file}`];
  if (!url) throw new Error("The report index shard is unavailable");
  const response = await fetch(url);
  if (!response.ok)
    throw new Error("The report index could not be loaded. Please try again.");
  const bytes = new Uint8Array(await response.arrayBuffer());
  const actual = [
    ...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
  ]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  if (actual !== shard.sha256)
    throw new Error("The report index integrity check failed");
  const data = JSON.parse(strFromU8(gunzipSync(bytes))) as {
    passages: EvidencePassage[];
  };
  if (data.passages.length !== shard.passages)
    throw new Error("The report index is incomplete");
  index.add(data.passages);
  loaded.add(key);
}
interface Request {
  id: number;
  question: string;
  filters: EvidenceFilters;
}
const scope = self as unknown as {
  onmessage: (event: MessageEvent<Request>) => void;
  postMessage: (data: unknown) => void;
};
scope.onmessage = ({ data }) => {
  queue = queue.then(async () => {
    try {
      const started = performance.now();
      const plan = planEvidenceSearch(data.question, data.filters);
      if (!plan.unsupported) {
        await load("timeline");
        const fed =
          (!plan.countries.length || plan.countries.includes("USA")) &&
          (!plan.institutions.length || plan.institutions.includes("Fed"));
        if (fed) {
          const wantedYears = new Set(plan.years);
          // December meeting minutes can be published in January of the next year.
          if (plan.dateField === "event")
            for (const year of plan.years)
              wantedYears.add(String(Number(year) + 1));
          const years = manifest.shards.filter(
            (s) =>
              s.key !== "timeline" &&
              (!plan.years.length || wantedYears.has(s.key)),
          );
          // Bounded concurrency keeps broad searches responsive without a model server.
          for (let i = 0; i < years.length; i += 4)
            await Promise.all(years.slice(i, i + 4).map((s) => load(s.key)));
        }
      }
      const result = index.search(data.question, data.filters);
      result.elapsedMs = performance.now() - started;
      scope.postMessage({ id: data.id, result, loadedPassages: index.size });
    } catch (error) {
      scope.postMessage({
        id: data.id,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  });
};
