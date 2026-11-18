import type { EvidenceAnswer, EvidenceFilters } from "./reportSearch";

export class ReportEvidenceClient {
  private worker?: Worker;
  private nextId = 0;
  private pending = new Map<
    number,
    { resolve: (r: EvidenceAnswer) => void; reject: (e: Error) => void }
  >();
  search(
    question: string,
    filters: EvidenceFilters = {},
  ): Promise<EvidenceAnswer> {
    if (!this.worker) {
      const worker = new Worker(
        new URL("./reportSearch.worker.ts", import.meta.url),
        { type: "module", name: "macrolab-report-evidence" },
      );
      worker.onmessage = ({
        data,
      }: MessageEvent<{
        id: number;
        result?: EvidenceAnswer;
        error?: string;
      }>) => {
        const request = this.pending.get(data.id);
        if (!request) return;
        this.pending.delete(data.id);
        if (data.error || !data.result)
          request.reject(
            new Error(data.error ?? "The search returned no response"),
          );
        else request.resolve(data.result);
      };
      worker.onerror = () =>
        this.dispose("The report search could not start. Please try again.");
      this.worker = worker;
    }
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      this.pending.set(id, { resolve, reject });
      this.worker!.postMessage({ id, question, filters });
    });
  }
  dispose(message = "Search cancelled") {
    this.worker?.terminate();
    this.worker = undefined;
    for (const request of this.pending.values())
      request.reject(new Error(message));
    this.pending.clear();
  }
}
