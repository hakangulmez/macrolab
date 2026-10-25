import { useEffect, useRef, useState } from "react";
import type { Manifest } from "../types";
import { coverage, datasetCounts, type CoverageCell } from "../uiData";
import { countryIndicators } from "../displayLabels";
import { Status } from "./Common";
export function SeriesSearch({
  manifest,
  select,
}: {
  manifest: Manifest | null;
  select: (cell: CoverageCell) => void;
}) {
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (manifest) setOpen(true);
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [manifest]);
  useEffect(() => {
    if (open) {
      dialog.current?.showModal();
      input.current?.focus();
    } else dialog.current?.close();
  }, [open]);
  const matches = manifest
    ? coverage(manifest)
        .filter(
          (c) =>
            c.observations > 0 &&
            query
              .toLowerCase()
              .split(/\s+/)
              .every((word) =>
                `${manifest.countries.find((x) => x.iso3 === c.country)?.name} ${c.country} ${manifest.indicators.find((i) => i.concept_id === c.concept_id)?.title} ${c.concept_id}`
                  .toLowerCase()
                  .includes(word),
              ),
        )
        .slice(0, 10)
    : [];
  return (
    <>
      <button
        className="header-search"
        disabled={!manifest}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <span>
          Search{" "}
          {manifest
            ? datasetCounts(manifest).populated.toLocaleString("en")
            : "…"}{" "}
          series…
        </span>
        <kbd>⌘ K</kbd>
      </button>
      <dialog
        ref={dialog}
        className="search-dialog"
        aria-labelledby="series-search-title"
        onClose={() => setOpen(false)}
      >
        <div className="row between">
          <h2 id="series-search-title">Find a series</h2>
          <button
            onClick={() => setOpen(false)}
            aria-label="Close series search"
          >
            Close
          </button>
        </div>
        <label className="field">
          <span>Economy or indicator</span>
          <input
            ref={input}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Try Germany CPI or real GDP"
          />
        </label>
        <p className="small muted">
          Populated series only. Explore the dataset to see missing cells.
        </p>
        <div className="search-matches">
          {matches.map((c) => (
            <button
              key={`${c.country}:${c.concept_id}`}
              onClick={() => {
                setOpen(false);
                select(c);
              }}
            >
              <span>
                <strong>
                  {manifest?.countries.find((x) => x.iso3 === c.country)?.name}
                </strong>
                <span>
                  {
                    countryIndicators(manifest!.indicators, c.country).find(
                      (i) => i.concept_id === c.concept_id,
                    )?.title
                  }
                </span>
              </span>
              <Status status={c.status} />
            </button>
          ))}
          {!matches.length && (
            <p>No populated series match. Try an economy name or indicator.</p>
          )}
        </div>
      </dialog>
    </>
  );
}
