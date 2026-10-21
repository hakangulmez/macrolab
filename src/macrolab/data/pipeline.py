"""G1 fetch, immutable raw snapshot, harmonisation, validation and local publication."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from macrolab.data.audit import audit_data
from macrolab.data.countries import enrich_country_metadata
from macrolab.data.coverage import build_coverage
from macrolab.data.harmonise import derive_term_spread, harmonise, splice_policy_rates
from macrolab.data.snapshot import SnapshotClient, SnapshotError, sha256_file, verify_raw_manifest
from macrolab.data.sources.bis import fetch_bis
from macrolab.data.sources.ecb import fetch_ecb
from macrolab.data.sources.eurostat import fetch_eurostat
from macrolab.data.sources.g11_cli import fetch_cli
from macrolab.data.sources.g11_prices import fetch_prices
from macrolab.data.sources.imf import fetch_imf
from macrolab.data.sources.oecd import fetch_countries, fetch_oecd
from macrolab.data.sources.worldbank import fetch_worldbank
from macrolab.data.standardise import standardise
from macrolab.data.validate import validate


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
        ).encode()
    ).hexdigest()


def processing_inputs(root: Path, concepts: list[dict[str, Any]]) -> dict[str, Any]:
    files = sorted((root / "src/macrolab/data").rglob("*.py")) + [
        root / name
        for name in (
            "configs/data_rules.yaml",
            "configs/country_notes.yaml",
            "configs/oecd_mappings.yaml",
            "configs/supplemental_mappings.yaml",
            "uv.lock",
            "pyproject.toml",
        )
    ]
    files += sorted((root / "configs").glob("g11_*.yaml"))
    hashes = {str(path.relative_to(root)): sha256_file(path) for path in files}
    # Generated country mappings describe output and must not become input to selection.
    definitions = [
        {
            key: value
            for key, value in concept.items()
            if key not in {"country_mappings", "mapping_status", "mapping_note"}
        }
        for concept in concepts
    ]
    payload = {"files": hashes, "concept_definitions_sha256": canonical_hash(definitions)}
    return {**payload, "fingerprint": canonical_hash(payload)}


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    """Store JSON metadata as strings so heterogeneous source attributes stay lossless."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for row in rows:
        records.append(
            {
                key: json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
                if isinstance(value, (dict, list, tuple))
                else value
                for key, value in row.items()
            }
        )
    frame = pd.DataFrame(records)
    frame.to_parquet(path, index=False, engine="pyarrow", compression="zstd")


def collect(client: SnapshotClient, *, include_g11: bool = False) -> dict[str, Any]:
    countries = enrich_country_metadata(fetch_countries(client), client)
    if not countries or len({country["iso3"] for country in countries}) != len(countries):
        raise SnapshotError("Official membership list is empty or duplicated")
    result: dict[str, Any] = {
        "countries": countries,
        "rows": [],
        "variant_rows": [],
        "profiles": [],
        "issues": [],
        "source_details": {},
    }
    for name, fetch in (
        ("OECD", fetch_oecd),
        ("BIS", fetch_bis),
        ("IMF", fetch_imf),
        ("ECB", fetch_ecb),
        ("Eurostat", fetch_eurostat),
        ("WorldBank", fetch_worldbank),
    ):
        started = time.perf_counter()
        print(json.dumps({"phase": "fetch", "source": name, "offline": client.offline}), flush=True)
        try:
            response = fetch(client, countries)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            response = {
                "rows": [],
                "issues": [{"source": name, "code": "adapter_failed", "detail": str(exc)}],
            }
        for key in ("rows", "variant_rows", "profiles", "issues"):
            result[key].extend(response.get(key, []))
        details = {
            key: value
            for key, value in response.items()
            if key not in {"rows", "variant_rows", "profiles", "countries"}
        }
        result["source_details"][name] = details
        print(
            json.dumps(
                {
                    "phase": "fetched",
                    "source": name,
                    "candidate_rows": len(response.get("rows", [])),
                    "issues": len(response.get("issues", [])),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            ),
            flush=True,
        )
    if include_g11:
        # New full snapshots use the corrected mappings too. Historical G1
        # replays do not request responses absent from their immutable archive.
        for name, correction in (("G1_1_prices", fetch_prices), ("G1_1_cli", fetch_cli)):
            response = correction(client, countries)
            if name == "G1_1_cli":
                result["rows"] = [r for r in result["rows"] if r["concept_id"] != "cli"]
                result["issues"] = [i for i in result["issues"] if i.get("concept_id") != "cli"]
            result["rows"].extend(response["rows"])
            result["issues"].extend(response.get("issues", []))
            result["source_details"][name] = {
                key: value for key, value in response.items() if key != "rows"
            }
    return result


def mapping_summary(
    cards: list[dict[str, Any]], selections: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "cells": len(cards),
        "status_counts": dict(Counter(card["status"] for card in cards)),
        "by_concept": {
            concept: {
                status: sum(
                    card["concept_id"] == concept and card["status"] == status for card in cards
                )
                for status in ("available", "available_note", "limited", "missing")
            }
            for concept in sorted({card["concept_id"] for card in cards})
        },
        "fallback_count": sum(selection["fallback"] for selection in selections),
        "stale_cells": sum(card["stale"] for card in cards),
        "reason_counts_by_concept": {
            concept: dict(
                Counter(
                    reason
                    for card in cards
                    if card["concept_id"] == concept
                    for reason in card.get("reason_codes", [])
                )
            )
            for concept in sorted({card["concept_id"] for card in cards})
        },
    }


def publish(
    root: Path,
    snapshot_id: str,
    collected: dict[str, Any],
    concepts: list[dict[str, Any]],
    rules: dict[str, Any],
    as_of: date,
    *,
    offline: bool,
) -> dict[str, Any]:
    rows, schema_issues = standardise(collected["rows"])
    variants, variant_issues = standardise(collected["variant_rows"])
    print(
        json.dumps({"phase": "standardised", "rows": len(rows), "rejected": len(schema_issues)}),
        flush=True,
    )
    if "prepared_selection" in collected:
        prepared = collected["prepared_selection"]
        selected, losing = prepared["selected"], prepared["losing"]
        selections, selection_issues = prepared["selections"], prepared["issues"]
        splice_issues: list[dict[str, Any]] = []
    else:
        selected, losing, selections, selection_issues = harmonise(
            rows, collected["countries"], concepts, rules
        )
        selected, splice_issues = splice_policy_rates(selected, collected["countries"])
        selected.extend(derive_term_spread(selected))
    adjustment_groups: dict[str, set[str]] = {}
    for row in selected:
        if row["sa_flag"] in {"SA", "NSA"}:
            adjustment_groups.setdefault(row["concept_id"], set()).add(row["sa_flag"])
    for row in selected:
        if len(adjustment_groups.get(row["concept_id"], set())) > 1:
            row["flags"] = sorted(set(row["flags"] + ["cross_country_adjustment_mismatch"]))
    selected.sort(key=lambda row: (row["country"], row["concept_id"], row["date"], row["freq"]))
    issues = collected["issues"] + schema_issues + variant_issues + selection_issues + splice_issues
    validation = validate(selected, rules)
    coverage, cards = build_coverage(
        selected, collected["countries"], concepts, rules, as_of, issues
    )
    print(
        json.dumps(
            {
                "phase": "audit",
                "rows": len(selected),
                "coverage": dict(Counter(row["status"] for row in coverage)),
            }
        ),
        flush=True,
    )
    audit_scope = collected.get("audit_scope", [concept["concept_id"] for concept in concepts])
    audit = audit_data(
        root,
        selected,
        [c for c in concepts if c["concept_id"] in audit_scope],
        collected.get("audit_countries"),
    )
    unchanged_proof = collected.get("unchanged_proof")
    if unchanged_proof:
        unchanged_proof["component_after_hashes"] = {
            "profiles": canonical_hash(collected["profiles"]),
            "variants": canonical_hash(variants),
            "countries": canonical_hash(collected["countries"]),
        }
        for component in ("profiles", "variants", "countries"):
            unchanged_proof[f"{component}_unchanged"] = (
                unchanged_proof["component_before_hashes"][component]
                == unchanged_proof["component_after_hashes"][component]
            )
        unchanged_proof["after_hash"] = canonical_hash(
            [row for row in selected if row["concept_id"] in unchanged_proof["concept_ids"]]
        )
        unchanged_proof["passed"] = unchanged_proof["before_hash"] == unchanged_proof[
            "after_hash"
        ] and all(
            unchanged_proof[key]
            for key in ("profiles_unchanged", "variants_unchanged", "countries_unchanged")
        )
    inputs = processing_inputs(root, concepts)
    if collected.get("processing_inputs", inputs) != inputs:
        raise SnapshotError("Processing code or configuration changed during this build")
    current_manifest = root / "data/processed/current/processed_manifest.json"
    baseline = json.loads(current_manifest.read_text()) if current_manifest.is_file() else None
    digest = canonical_hash(selected)
    destination = root / "data/processed/snapshots" / snapshot_id
    if offline and destination.exists():
        destination = (
            root
            / "data/processed/rebuilds"
            / snapshot_id
            / datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        )
    destination.mkdir(parents=True, exist_ok=False)
    write_parquet(destination / "series.parquet", selected)
    for concept in concepts:
        subset = [row for row in selected if row["concept_id"] == concept["concept_id"]]
        write_parquet(destination / "by_concept" / f"{concept['concept_id']}.parquet", subset)
    write_parquet(destination / "candidate_series.parquet", losing)
    write_parquet(destination / "variant_series.parquet", variants)
    write_parquet(destination / "coverage.parquet", coverage)
    write_parquet(destination / "profiles.parquet", collected["profiles"])
    write_json(destination / "countries.json", collected["countries"])
    write_json(destination / "series_cards.json", cards)
    write_json(destination / "fallbacks.json", [item for item in selections if item["fallback"]])
    write_json(destination / "selection_ledger.json", selections)
    write_json(destination / "issues.json", issues)
    write_json(destination / "validation.json", validation)
    write_json(destination / "audit.json", audit)
    write_json(destination / "source_details.json", collected["source_details"])
    variant_bundle = {}
    for variant in sorted({row.get("variant", "default") for row in variants}):
        values = [row for row in variants if row.get("variant", "default") == variant]
        values.sort(key=lambda row: row["date"])
        variant_bundle[variant] = {
            "metadata": {
                key: values[0].get(key)
                for key in (
                    "concept_id",
                    "source",
                    "source_series_id",
                    "unit",
                    "unit_mult",
                    "base_year",
                    "freq",
                    "sa_flag",
                    "price_basis",
                    "attribution",
                    "source_url",
                    "terms_status",
                )
            },
            "observations": [
                [row["date"], row["value"], row["obs_status"], row["flags"]] for row in values
            ],
        }
    write_json(
        destination / "browser/global-variants.json",
        {"snapshot_id": snapshot_id, "variants": variant_bundle, "publication_approved": False},
        compact=True,
    )
    for country in collected["countries"]:
        iso3 = country["iso3"]
        compact = {
            "snapshot_id": snapshot_id,
            "as_of_date": as_of.isoformat(),
            "country": country,
            "cards": [card for card in cards if card["country"] == iso3],
            "series": {
                concept["concept_id"]: [
                    [row["date"], row["value"], row["obs_status"], row["flags"]]
                    for row in selected
                    if row["country"] == iso3 and row["concept_id"] == concept["concept_id"]
                ]
                for concept in concepts
            },
            "profiles": [
                profile for profile in collected["profiles"] if profile["country"] == iso3
            ],
            "global_variants_ref": "global-variants.json",
            "publication_approved": False,
        }
        write_json(destination / "browser" / f"{iso3}.json", compact, compact=True)
    files = {
        str(path.relative_to(destination)): {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    code_version = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    manifest = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "as_of_date": as_of.isoformat(),
        "built_utc": datetime.now(UTC).isoformat(),
        "offline_rebuild": offline,
        "destination": str(destination.relative_to(root)),
        "code_version": code_version,
        "code_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        ),
        "processing_inputs": inputs,
        "observations_hash": digest,
        "observations": len(selected),
        "countries": len(collected["countries"]),
        "national_concepts": sum(concept["scope"] == "national" for concept in concepts),
        "global_factors": sum(concept["scope"] == "global" for concept in concepts),
        "coverage_summary": mapping_summary(cards, selections),
        "audit_summary": {
            key: audit[key]
            for key in (
                "required_checks",
                "performed_checks",
                "matched",
                "mismatches",
                "unavailable",
                "passed",
            )
        },
        "audit_scope": audit_scope,
        "base_snapshot": collected.get("base_snapshot"),
        "unchanged_proof": unchanged_proof,
        "raw_verification": verify_raw_manifest(root, snapshot_id),
        "files": files,
        "data_policy": "local only; no redistribution of raw data",
    }
    if offline and baseline and baseline.get("snapshot_id") == snapshot_id:
        same_inputs = baseline.get("processing_inputs") == inputs
        manifest["replay_comparison"] = {
            "baseline_destination": baseline["destination"],
            "same_processing_inputs": same_inputs,
            "observations_match": digest == baseline["observations_hash"],
            "coverage_match": (
                files["coverage.parquet"]["sha256"]
                == baseline["files"]["coverage.parquet"]["sha256"]
            ),
            "note": "Exact replay required for unchanged processing inputs; changed builds "
            "retain their prior output and record a new implementation fingerprint.",
        }
    replay = manifest.get("replay_comparison", {})
    manifest["validation_passed"] = bool(
        audit["passed"]
        and (unchanged_proof is None or unchanged_proof["passed"])
        and not schema_issues
        and not variant_issues
        and (
            not replay.get("same_processing_inputs")
            or (replay["observations_match"] and replay["coverage_match"])
        )
    )
    write_json(destination / "processed_manifest.json", manifest)
    if not manifest["validation_passed"]:
        raise SnapshotError(
            f"Validation failed; diagnostics retained at {destination}; current not promoted"
        )
    # Only the mutable local pointer changes. Snapshot directories are never replaced.
    pointer = root / "data/processed/current"
    temporary = root / "data/processed/.next-current"
    temporary.symlink_to(destination.relative_to(pointer.parent), target_is_directory=True)
    temporary.replace(pointer)
    for name in ("series.parquet", "coverage.parquet"):
        link = root / "data/processed" / name
        if not link.exists() and not link.is_symlink():
            link.symlink_to(Path("current") / name)
    write_json(root / "data/manifests/processed_manifest.json", manifest)
    return manifest


def run(root: Path, *, snapshot_id: str | None = None, offline: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    if offline and not snapshot_id:
        raise SnapshotError("Offline rebuild requires an explicit snapshot ID")
    snapshot_id = snapshot_id or datetime.now(UTC).strftime("%Y%m%d-%H%M")
    if not all(character.isdigit() or character == "-" for character in snapshot_id):
        raise SnapshotError("Invalid snapshot identifier")
    marker = root / "data/manifests/snapshots" / f"{snapshot_id}.json"
    if offline:
        state = json.loads(marker.read_text())
        if state.get("gate") == "G1_1":
            from macrolab.data.correction import run_correction

            return run_correction(root, snapshot=snapshot_id, offline=True)
        as_of = date.fromisoformat(state["as_of_date"])
    else:
        if marker.exists():
            raise SnapshotError("Snapshot already exists; use offline replay or a new timestamp")
        as_of = datetime.now(UTC).date()
        marker.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            marker,
            {
                "snapshot_id": snapshot_id,
                "as_of_date": as_of.isoformat(),
                "status": "fetching",
                "source_revision": "G1_1",
            },
        )
    client = SnapshotClient(root, snapshot_id, offline=offline, as_of_date=as_of)
    config = yaml.safe_load((root / "configs/indicators.yaml").read_text())
    rules = yaml.safe_load((root / "configs/data_rules.yaml").read_text())
    rules["as_of_date"] = as_of.isoformat()
    inputs = processing_inputs(root, config["concepts"])
    include_g11 = not offline or state.get("source_revision") == "G1_1"
    collected = collect(client, include_g11=include_g11)
    collected["processing_inputs"] = inputs
    manifest = publish(
        root, snapshot_id, collected, config["concepts"], rules, as_of, offline=offline
    )
    if not offline or state.get("status") != "complete":
        write_json(
            marker,
            {
                "snapshot_id": snapshot_id,
                "as_of_date": as_of.isoformat(),
                "status": "complete",
                "source_revision": "G1_1" if include_g11 else "G1",
                "processed_manifest": manifest["destination"] + "/processed_manifest.json",
            },
        )
    print(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "observations": manifest["observations"],
                "coverage": manifest["coverage_summary"],
                "audit": manifest["audit_summary"],
                "offline_rebuild": offline,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        ),
        flush=True,
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    run(Path.cwd(), snapshot_id=args.snapshot, offline=args.offline)


if __name__ == "__main__":
    main()
