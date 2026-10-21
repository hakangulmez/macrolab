"""G1.1: replace only price/CLI candidates; freeze all other accepted G1 observations."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq
import yaml

from macrolab.data.coverage import build_coverage
from macrolab.data.harmonise import harmonise
from macrolab.data.pipeline import canonical_hash, processing_inputs, publish, write_json
from macrolab.data.snapshot import SnapshotClient, SnapshotError, sha256_file, verify_raw_manifest
from macrolab.data.sources.g11_cli import fetch_cli
from macrolab.data.sources.g11_prices import fetch_prices
from macrolab.data.standardise import standardise

TARGETS = {"ppi", "cpi", "cpi_core", "cli"}
JSON_COLUMNS = {"audit", "flags", "source_metadata", "component_urls"}


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Restore nested metadata explicitly; do not interpret a flag string as characters."""
    # PyArrow exposes this reader without a typed signature.
    records: list[dict[str, Any]] = pq.read_table(path).to_pylist()  # type: ignore[no-untyped-call]
    for row in records:
        for key in JSON_COLUMNS:
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])
        if "flags" in row and (
            not isinstance(row["flags"], list)
            or any(not isinstance(flag, str) for flag in row["flags"])
        ):
            raise ValueError("Stored observation flags must be a list of strings")
    return records


def row_order(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return row["country"], row["concept_id"], row["date"], row["freq"]


def prepare(
    root: Path,
    base: Path,
    prices: dict[str, Any],
    cli: dict[str, Any],
    concepts: list[dict[str, Any]],
    rules: dict[str, Any],
    as_of: date,
) -> dict[str, Any]:
    original = json.loads((base / "processed_manifest.json").read_text())
    if not original.get("validation_passed") or not original["audit_summary"]["passed"]:
        raise SnapshotError("Correction requires an accepted audited baseline")
    for name, expected in original["files"].items():
        if sha256_file(base / name) != expected["sha256"]:
            raise SnapshotError(f"Baseline output checksum mismatch: {name}")
    verify_raw_manifest(root, original["snapshot_id"])
    countries = json.loads((base / "countries.json").read_text())
    before = read_rows(base / "series.parquet")
    before.sort(key=row_order)
    losing = read_rows(base / "candidate_series.parquet")
    untouched = [row for row in before if row["concept_id"] not in TARGETS]
    additions, rejected = standardise(prices["rows"] + cli["rows"])
    if rejected or any(row["concept_id"] not in TARGETS for row in additions):
        raise SnapshotError("Correction source rows violate schema or authorized concept scope")
    new_keys = {(row["source"], row["source_series_id"]) for row in additions}
    # A newly retrieved series replaces its entire prior vintage. CLI is verified
    # against its full current flow; no confidence indicator is part of this refresh.
    candidates = [
        row
        for row in before + losing
        if row["concept_id"] in TARGETS - {"cli"}
        and (row["source"], row["source_series_id"]) not in new_keys
    ] + additions
    for row in candidates:
        row.pop("selection_status", None)
        if row.get("candidate_priority") is None:
            row.pop("candidate_priority", None)
    chosen, rejected_candidates, selections, selection_issues = harmonise(
        candidates, countries, [c for c in concepts if c["concept_id"] in TARGETS], rules
    )
    selected = sorted(untouched + chosen, key=row_order)
    previous_issues = json.loads((base / "issues.json").read_text())
    issues = [issue for issue in previous_issues if issue.get("concept_id") not in TARGETS]
    issues += prices.get("issues", []) + cli.get("issues", [])
    baseline_coverage, _ = build_coverage(
        before, countries, concepts, rules, as_of, previous_issues
    )
    previous_selections = json.loads((base / "selection_ledger.json").read_text())
    variants = read_rows(base / "variant_series.parquet")
    profiles = read_rows(base / "profiles.parquet")
    return {
        "rows": additions,
        "countries": countries,
        "variant_rows": variants,
        "profiles": profiles,
        "issues": issues,
        "source_details": {
            "G1_1_prices": {k: v for k, v in prices.items() if k != "rows"},
            "G1_1_cli": {k: v for k, v in cli.items() if k != "rows"},
            "base_source_details": str((base / "source_details.json").relative_to(root)),
        },
        "prepared_selection": {
            "selected": selected,
            "losing": [row for row in losing if row["concept_id"] not in TARGETS]
            + rejected_candidates,
            "selections": [s for s in previous_selections if s["concept_id"] not in TARGETS]
            + selections,
            "issues": selection_issues,
        },
        "audit_scope": sorted(TARGETS),
        "audit_countries": {
            "ppi": ["DEU", "FRA", "ITA"],
            "cpi": ["JPN", "MEX", "CHL"],
            "cpi_core": ["JPN", "CRI", "CAN"],
            "cli": ["USA", "DEU", "JPN"],
        },
        "base_snapshot": {
            "snapshot_id": original["snapshot_id"],
            "destination": str(base.relative_to(root)),
            "manifest_sha256": sha256_file(base / "processed_manifest.json"),
            "audit_summary": original["audit_summary"],
        },
        "unchanged_proof": {
            "concept_ids": sorted(
                c["concept_id"] for c in concepts if c["concept_id"] not in TARGETS
            ),
            "before_hash": canonical_hash(untouched),
            "after_hash": None,
            "passed": False,
            "rows": len(untouched),
            "component_before_hashes": {
                "profiles": canonical_hash(profiles),
                "variants": canonical_hash(variants),
                "countries": canonical_hash(countries),
            },
            "profiles_unchanged": False,
            "variants_unchanged": False,
            "countries_unchanged": False,
        },
        "baseline_coverage": baseline_coverage,
    }


def run_correction(
    root: Path, *, snapshot: str | None = None, offline: bool = False
) -> dict[str, Any]:
    local_now = datetime.now(ZoneInfo("Europe/Berlin"))
    if offline and not snapshot:
        raise SnapshotError("Offline correction requires a snapshot ID")
    snapshot = snapshot or local_now.strftime("%Y%m%d-%H%M")
    if not re.fullmatch(r"\d[\d-]*", snapshot):
        raise SnapshotError("Invalid snapshot identifier")
    marker = root / "data/manifests/snapshots" / f"{snapshot}.json"
    if offline:
        state = json.loads(marker.read_text())
        if state.get("gate") != "G1_1":
            raise SnapshotError("This snapshot is not a G1.1 correction")
    else:
        if marker.exists():
            raise SnapshotError("Snapshot exists; use offline replay")
        base = (root / "data/processed/current").resolve()
        state = {
            "gate": "G1_1",
            "snapshot_id": snapshot,
            "as_of_date": local_now.date().isoformat(),
            "base_destination": str(base.relative_to(root)),
            "status": "fetching",
        }
        write_json(marker, state)
    base = (root / state["base_destination"]).resolve()
    if not base.is_relative_to((root / "data/processed").resolve()):
        raise SnapshotError("Baseline must be a local processed snapshot")
    as_of = date.fromisoformat(state["as_of_date"])
    countries = json.loads((base / "countries.json").read_text())
    client = SnapshotClient(root, snapshot, offline=offline, as_of_date=as_of)
    concepts = yaml.safe_load((root / "configs/indicators.yaml").read_text())["concepts"]
    for concept in concepts:
        if concept["concept_id"] == "ppi":
            concept["source_priority"] = ["OECD", "Eurostat"]
    rules = yaml.safe_load((root / "configs/data_rules.yaml").read_text())
    rules["as_of_date"] = as_of.isoformat()
    inputs = processing_inputs(root, concepts)
    print(json.dumps({"snapshot": snapshot, "phase": "prices", "offline": offline}), flush=True)
    prices = fetch_prices(client, countries)
    print(json.dumps({"phase": "cli"}), flush=True)
    cli = fetch_cli(client, countries)
    collected = prepare(root, base, prices, cli, concepts, rules, as_of)
    collected["processing_inputs"] = inputs
    write_json(root / "runs/g1_1/baseline_coverage.json", collected.pop("baseline_coverage"))
    result = publish(root, snapshot, collected, concepts, rules, as_of, offline=offline)
    if state.get("status") != "complete":
        state.update(
            {
                "status": "complete",
                "processed_manifest": result["destination"] + "/processed_manifest.json",
            }
        )
        write_json(marker, state)
    print(
        json.dumps(
            {
                "snapshot": snapshot,
                "coverage": result["coverage_summary"],
                "audit": result["audit_summary"],
                "unchanged": result["unchanged_proof"],
            }
        ),
        flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    run_correction(Path.cwd(), snapshot=args.snapshot, offline=args.offline)


if __name__ == "__main__":
    main()
