"""Publish G1_1 metadata-only mappings from a completed, locally verified snapshot.

Run only after the full snapshot is ready. This script reads no remote service and
copies no observation values. --check validates the proposed catalogue without
writing it. Audit limitations are retained; this is not a G1 acceptance command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from macrolab.catalogue import (
    MAPPING_FIELDS,
    SOURCE_FIELDS,
    CatalogueError,
    aggregation_rules,
    mapping_status,
    project_root,
    validate_catalogue,
)

CONCEPT_FIELDS = (
    "concept_id",
    "title",
    "scope",
    "native_frequency",
    "default_transform",
    "source_priority",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_document(
    existing: dict[str, Any],
    cards: list[dict[str, Any]],
    manifest: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Build a validated document using only explicitly allowed metadata fields."""
    concepts = validate_catalogue(existing)
    expected = {concept.concept_id for concept in concepts}
    by_concept: dict[str, dict[str, Any]] = {concept_id: {} for concept_id in expected}
    for card in cards:
        concept_id, country = card.get("concept_id"), card.get("country")
        if concept_id not in expected or not isinstance(country, str):
            raise CatalogueError("Series cards contain an unknown concept or invalid country.")
        if country in by_concept[concept_id]:
            raise CatalogueError(f"Duplicate series card: {country}/{concept_id}.")
        entry = {field: card.get(field) for field in sorted(MAPPING_FIELDS)}
        segments = card.get("source_segments")
        if not isinstance(segments, list) or any(not isinstance(item, dict) for item in segments):
            raise CatalogueError(f"Invalid source segments: {country}/{concept_id}.")
        entry["source_segments"] = [
            {field: segment.get(field) for field in sorted(SOURCE_FIELDS)} for segment in segments
        ]
        by_concept[concept_id][country] = entry
    countries = sorted({country for entries in by_concept.values() for country in entries})
    if not countries or manifest.get("countries") != len(countries):
        raise CatalogueError("Manifest country count does not match series cards.")
    if any(set(entries) != set(countries) for entries in by_concept.values()):
        raise CatalogueError(
            "Series cards must cover every concept and country, including missing cells."
        )
    if any(type(card.get("observations")) is not int for card in cards):
        raise CatalogueError("Series cards require integer observation counts.")
    if sum(card["observations"] for card in cards) != manifest.get("observations"):
        raise CatalogueError("Manifest observation count does not match series cards.")
    if manifest.get("national_concepts") != sum(item.scope == "national" for item in concepts):
        raise CatalogueError("Manifest national concept count differs from the catalogue.")
    if manifest.get("global_factors") != sum(item.scope == "global" for item in concepts):
        raise CatalogueError("Manifest global factor count differs from the catalogue.")
    definitions = []
    for original in existing["concepts"]:
        concept_id = original["concept_id"]
        mappings = dict(sorted(by_concept[concept_id].items()))
        definitions.append(
            {
                **{field: original[field] for field in CONCEPT_FIELDS},
                "mapping_status": mapping_status(mappings),
                "aggregation_rules": aggregation_rules(concept_id),
                "country_mappings": mappings,
            }
        )
    result = {
        "schema_version": 1,
        "stage": "G1_1",
        "mapping_status": "snapshot_verified_with_explicit_coverage_limits",
        "mapping_note": (
            "Selected series metadata was checked against a completed local snapshot. "
            "Available, available with notes, limited and missing coverage are distinct; "
            "shorter history beginning through 2005-12-31 is a note, while a later start "
            "after the requested sample is limited. Verified mappings do not "
            "imply a passed gate, permission to redistribute data, or publication approval. "
            "Source observations remain under ignored data/."
        ),
        "default_transform_note": existing.get("default_transform_note", "Concept defaults only."),
        "default_sample_start": existing.get("default_sample_start", "1999-Q1"),
        "snapshot_provenance": {
            **provenance,
            "country_codes": countries,
            "country_count": len(countries),
        },
        "concepts": definitions,
    }
    validate_catalogue(result)
    return result


def proposed_catalogue(root: Path) -> dict[str, Any]:
    """Require the current pointer, completion marker, manifest and cards to agree."""
    root = root.resolve()
    processed = (root / "data/processed").resolve()
    current = (processed / "current").resolve(strict=True)
    if not current.is_relative_to(processed) or current == processed:
        raise CatalogueError("Current snapshot must remain inside project data/processed.")
    manifest_path = current / "processed_manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise CatalogueError("Invalid processed manifest.")
    snapshot = manifest.get("snapshot_id")
    if not isinstance(snapshot, str) or not re.fullmatch(r"\d[\d-]*", snapshot):
        raise CatalogueError("Invalid snapshot identifier.")
    if manifest.get("destination") != str(current.relative_to(root)):
        raise CatalogueError("Processed manifest destination differs from the current pointer.")
    marker = json.loads((root / "data/manifests/snapshots" / f"{snapshot}.json").read_text())
    if (
        marker.get("status") != "complete"
        or marker.get("snapshot_id") != snapshot
        or marker.get("as_of_date") != manifest.get("as_of_date")
    ):
        raise CatalogueError("Snapshot is incomplete or its completion marker disagrees.")
    original_manifest = root / "data/processed/snapshots" / snapshot / "processed_manifest.json"
    if manifest.get("offline_rebuild"):
        expected_marker = str(original_manifest.relative_to(root))
        replay = manifest.get("replay_comparison")
        if not isinstance(replay, dict) or any(
            type(replay.get(key)) is not bool
            for key in ("same_processing_inputs", "observations_match", "coverage_match")
        ):
            raise CatalogueError("Offline rebuild needs an explicit replay comparison.")
        if replay["same_processing_inputs"] and not (
            replay["observations_match"] and replay["coverage_match"]
        ):
            raise CatalogueError("Identical processing inputs did not reproduce the baseline.")
    else:
        expected_marker = str(manifest_path.relative_to(root))
    if marker.get("processed_manifest") != expected_marker:
        raise CatalogueError("Completion marker points to a different processed snapshot.")
    if manifest.get("validation_passed") is not True:
        raise CatalogueError("Processed snapshot has not passed validation.")
    if manifest.get("audit_summary", {}).get("passed") is not True:
        raise CatalogueError("Processed snapshot has not passed independent raw-value audits.")
    base = manifest.get("base_snapshot")
    if base is not None:
        if not isinstance(base, dict) or not isinstance(base.get("destination"), str):
            raise CatalogueError("Invalid base snapshot metadata.")
        base_path = (root / base["destination"] / "processed_manifest.json").resolve(strict=True)
        if not base_path.is_relative_to(processed):
            raise CatalogueError("Base snapshot must remain in project data/processed.")
        base_bytes = base_path.read_bytes()
        base_manifest = json.loads(base_bytes)
        if (
            _sha256(base_bytes) != base.get("manifest_sha256")
            or base_manifest.get("snapshot_id") != base.get("snapshot_id")
            or base_manifest.get("destination") != base.get("destination")
            or base_manifest.get("audit_summary") != base.get("audit_summary")
            or base_manifest.get("validation_passed") is not True
        ):
            raise CatalogueError("Base snapshot hash, identity or validation evidence disagrees.")
    cards_path = current / "series_cards.json"
    cards_bytes = cards_path.read_bytes()
    cards_record = manifest.get("files", {}).get("series_cards.json", {})
    if cards_record.get("sha256") != _sha256(cards_bytes) or cards_record.get("bytes") != len(
        cards_bytes
    ):
        raise CatalogueError("Series cards fail the processed-manifest hash/size check.")
    raw_verification = manifest.get("raw_verification", {})
    if not isinstance(raw_verification, dict) or not (
        type(raw_verification.get("response_hashes_verified")) is int
        and raw_verification["response_hashes_verified"] > 0
    ):
        raise CatalogueError("Processed manifest has no verified raw response hashes.")
    cards = json.loads(cards_bytes)
    if not isinstance(cards, list) or any(not isinstance(card, dict) for card in cards):
        raise CatalogueError("Series cards must be a list of metadata records.")
    existing = yaml.safe_load((root / "configs/indicators.yaml").read_text())
    provenance = {
        "snapshot_id": snapshot,
        "as_of_date": manifest.get("as_of_date"),
        "built_utc": manifest.get("built_utc"),
        "code_version": manifest.get("code_version"),
        "code_dirty": manifest.get("code_dirty"),
        "offline_rebuild": manifest.get("offline_rebuild"),
        "validation_passed": manifest.get("validation_passed"),
        "processing_inputs": {
            key: manifest.get("processing_inputs", {}).get(key)
            for key in ("files", "concept_definitions_sha256", "fingerprint")
        },
        "replay_comparison": {
            key: manifest["replay_comparison"].get(key)
            for key in (
                "baseline_destination",
                "same_processing_inputs",
                "observations_match",
                "coverage_match",
            )
        }
        if manifest.get("replay_comparison")
        else None,
        "processed_manifest_path": str(manifest_path.relative_to(root)),
        "processed_manifest_sha256": _sha256(manifest_bytes),
        "series_cards_path": str(cards_path.relative_to(root)),
        "series_cards_sha256": _sha256(cards_bytes),
        "observations_hash": manifest.get("observations_hash"),
        "raw_response_hashes_verified": raw_verification["response_hashes_verified"],
        "audit_summary": {
            key: manifest.get("audit_summary", {}).get(key)
            for key in (
                "required_checks",
                "performed_checks",
                "matched",
                "mismatches",
                "unavailable",
                "passed",
            )
        },
        "audit_scope": manifest.get("audit_scope"),
        "base_snapshot": {
            key: base.get(key)
            for key in ("snapshot_id", "destination", "manifest_sha256", "audit_summary")
        }
        if base is not None
        else None,
        "unchanged_proof": {
            key: manifest["unchanged_proof"].get(key)
            for key in (
                "concept_ids",
                "before_hash",
                "after_hash",
                "passed",
                "rows",
                "profiles_unchanged",
                "variants_unchanged",
                "countries_unchanged",
            )
        }
        if isinstance(manifest.get("unchanged_proof"), dict)
        else None,
        "verification": "completed_snapshot_and_cards_hash_verified",
    }
    return build_document(existing, cards, manifest, provenance)


def update_catalogue(root: Path, *, check: bool = False) -> dict[str, Any]:
    document = proposed_catalogue(root)
    if not check:
        destination = root.resolve() / "configs/indicators.yaml"
        if not destination.resolve().is_relative_to(root.resolve()):
            raise CatalogueError("Catalogue destination lies outside the project.")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=".indicators-",
                suffix=".yaml",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                yaml.safe_dump(document, handle, sort_keys=False, allow_unicode=True, width=100)
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {
        "written": not check,
        "snapshot_id": document["snapshot_provenance"]["snapshot_id"],
        "concepts": len(document["concepts"]),
        "countries": document["snapshot_provenance"]["country_count"],
        "status_counts": dict(
            sorted(Counter(concept["mapping_status"] for concept in document["concepts"]).items())
        ),
        "observation_values_written": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Validate without writing the catalogue"
    )
    args = parser.parse_args()
    print(json.dumps(update_catalogue(project_root(), check=args.check), indent=2))


if __name__ == "__main__":
    main()
