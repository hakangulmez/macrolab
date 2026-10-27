import type { Manifest } from "../types";
import type { RecentResult } from "../recentResults";

export function RecentResults({
  entries,
  manifest,
  busy,
  reopen,
}: {
  entries: RecentResult[];
  manifest: Manifest;
  busy: boolean;
  reopen: (entry: RecentResult) => void;
}) {
  return (
    <section className="recent-results section-v3" aria-label="Recent results">
      <h2>Recent results</h2>
      <p className="small muted">
        Reopen a saved configuration and run it again. Configurations stay in
        this browser; results use the recorded snapshot.
      </p>
      {entries.length ? (
        <ul className="recent-results-list">
          {entries.map((entry, index) => {
            const { config } = entry;
            const title =
              manifest.templates.find(
                (t) => t.id === config.model.params.template_id,
              )?.title ??
              manifest.models.find((m) => m.id === config.model.id)?.title ??
              config.model.id;
            return (
              <li key={index}>
                <button disabled={busy} onClick={() => reopen(entry)}>
                  <strong>{title}</strong>
                  <span className="small">
                    {config.countries
                      .map(
                        (iso) =>
                          manifest.countries.find((c) => c.iso3 === iso)
                            ?.name ?? iso,
                      )
                      .join(", ")}
                    {" · "}
                    {config.sample.start}–{config.sample.end}
                  </span>
                  <span className="small muted">
                    Snapshot {config.snapshot_id}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="small muted">Your completed runs will appear here.</p>
      )}
    </section>
  );
}
