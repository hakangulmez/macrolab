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
        {localOnly
          ? "Local comparison only · includes sources not cleared for publication."
          : "Static candidate · source exclusions are visible."}
      </strong>{" "}
      {localOnly ? (
        <>
          This build retains the full local snapshot for comparison and is not a
          publication candidate.{" "}
          {sources.length > 0 &&
            `Sources awaiting clearance: ${sources.join(", ")}. `}
        </>
      ) : (
        <>
          {sources.length > 0
            ? `Some observations from ${sources.join(", ")} are excluded under the source policy. `
            : "The source policy determines the included observations. "}
          Series cards identify the affected histories; estimates use only the
          included data.
        </>
      )}
      {publication.notes_withheld &&
        " Country notes are withheld pending review."}{" "}
      {!localOnly && publication.excluded_concepts?.length ? (
        <ul data-testid="excluded-concepts">
          {publication.excluded_concepts.map((concept) => (
            <li key={concept.concept_id}>
              <strong>{concept.title}.</strong> {concept.reason}
            </li>
          ))}
        </ul>
      ) : null}
      {openMethods && (
        <button className="link" onClick={openMethods}>
          View source policy
        </button>
      )}
    </aside>
  );
}
