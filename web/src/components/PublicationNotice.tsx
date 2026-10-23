import type { Manifest } from "../types";
import { text } from "../format";

export function PublicationNotice({
  manifest,
  openMethods,
}: {
  manifest: Manifest;
  openMethods?: () => void;
}) {
  const publication = manifest.publication;
  if (publication?.mode !== "static_candidate") return null;
  const localOnly =
    publication.local_only_comparison === true ||
    publication.source_mode === "all";
  if (!localOnly) return null;
  const sources = [
    ...new Set(
      publication.excluded_sources.map((source) =>
        [
          text(source.source, text(source.id)).replace(
            "WorldBank",
            "World Bank",
          ),
          text(source.dataset, ""),
        ]
          .filter(Boolean)
          .join(" · "),
      ),
    ),
  ];
  return (
    <aside
      className="info-box section small"
      aria-label="Publication data scope"
    >
      <strong>
        Local comparison only · includes sources not cleared for publication.
      </strong>{" "}
      This build retains the full local snapshot for comparison and is not a
      publication candidate.{" "}
      {sources.length > 0 &&
        `Sources awaiting clearance: ${sources.join(", ")}. `}
      {publication.notes_withheld &&
        " Country notes are withheld pending review."}{" "}
      {openMethods && (
        <button className="link" onClick={openMethods}>
          View source policy
        </button>
      )}
    </aside>
  );
}
