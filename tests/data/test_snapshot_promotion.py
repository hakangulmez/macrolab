"""Failed data checks retain diagnostics without replacing an accepted local snapshot."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from macrolab.data import pipeline
from macrolab.data.snapshot import SnapshotError

SNAPSHOT = "20261020-2358"
INPUT_FILES = (
    "src/macrolab/data/synthetic.py",
    "configs/data_rules.yaml",
    "configs/country_notes.yaml",
    "configs/oecd_mappings.yaml",
    "configs/supplemental_mappings.yaml",
    "configs/g16_stale_candidates.json",
    "uv.lock",
    "pyproject.toml",
)


def inputs(root: Path) -> list[dict[str, Any]]:
    for name in INPUT_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Synthetic processing input\n")
    return [
        {
            "concept_id": "rate_10y",
            "title": "Long-term rate",
            "scope": "national",
            "native_frequency": "M",
            "default_transform": "level",
            "source_priority": ["OECD"],
        }
    ]


def collection(root: Path) -> dict[str, Any]:
    relative = f"data/raw/OECD/{SNAPSHOT}/synthetic.csv"
    raw = root / relative
    raw.parent.mkdir(parents=True)
    lines = ["REF_AREA,TIME_PERIOD,OBS_VALUE"]
    countries = [{"iso3": code, "name": code} for code in ("USA", "DEU", "JPN")]
    rows = []
    for country in countries:
        code = country["iso3"]
        for month in (1, 2, 3):
            period = f"2026-{month:02d}"
            value = float(month + 1)
            lines.append(f"{code},{period},{value}")
            rows.append(
                {
                    "country": code,
                    "concept_id": "rate_10y",
                    "source": "OECD",
                    "source_series_id": f"synthetic/{code}/rate_10y",
                    "date": period,
                    "value": value,
                    "unit": "PA",
                    "unit_label": "Percent per annum",
                    "unit_mult": 0,
                    "sa_flag": "NA",
                    "price_basis": "not_applicable",
                    "base_year": None,
                    "freq": "M",
                    "obs_status": "reported",
                    "source_url": "https://sdmx.oecd.org/synthetic-promotion-fixture",
                    "attribution": "Synthetic test fixture",
                    "raw_path": relative,
                    "audit": {
                        "parser": "csv",
                        "source_period": period,
                        "selector": {"REF_AREA": code},
                    },
                    "flags": [],
                }
            )
    body = ("\n".join(lines) + "\n").encode()
    raw.write_bytes(body)
    record = {
        "snapshot_id": SNAPSHOT,
        "raw_path": relative,
        "body_complete": True,
        "sha256": hashlib.sha256(body).hexdigest(),
        "size_bytes": len(body),
    }
    manifest = root / "data/manifests/raw_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(record) + "\n")
    return {
        "countries": countries,
        "rows": rows,
        "variant_rows": [],
        "profiles": [],
        "issues": [],
        "source_details": {},
    }


@pytest.mark.parametrize("failure", ["audit_mismatch", "schema_rejection"])
def test_failed_candidate_retains_diagnostics_and_does_not_promote_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    concepts = inputs(tmp_path)
    collected = collection(tmp_path)
    if failure == "audit_mismatch":
        collected["rows"][0]["value"] += 1.0
    else:
        malformed = deepcopy(collected["rows"][0])
        del malformed["value"]
        collected["rows"].append(malformed)
    rules = {
        "requested_sample_start": "2026-01-01",
        "adequate_history": {"M": 3, "Q": 3, "A": 3},
        "plausibility": {"rate_10y": [-20, 300]},
        "elb_threshold_percent": 0.25,
        "staleness_months": {"M": 6, "Q": 9, "A": 24},
        "commodity_staleness_months": 3,
    }
    accepted = tmp_path / "data/processed/snapshots/accepted"
    accepted.mkdir(parents=True)
    accepted_manifest = '{"snapshot_id":"accepted","validation_passed":true}\n'
    (accepted / "processed_manifest.json").write_text(accepted_manifest)
    current = tmp_path / "data/processed/current"
    current.symlink_to(Path("snapshots/accepted"), target_is_directory=True)
    public_manifest = tmp_path / "data/manifests/processed_manifest.json"
    public_manifest.write_text(accepted_manifest)

    def git_output(command: list[str], **_kwargs: Any) -> str:
        return "a" * 40 if command[1] == "rev-parse" else " M synthetic.py\n"

    monkeypatch.setattr("macrolab.data.pipeline.subprocess.check_output", git_output)

    with pytest.raises(SnapshotError, match="Validation failed"):
        pipeline.publish(
            tmp_path, SNAPSHOT, collected, concepts, rules, date(2026, 4, 1), offline=False
        )

    assert current.resolve() == accepted
    assert public_manifest.read_text() == accepted_manifest
    diagnostics = tmp_path / "data/processed/snapshots" / SNAPSHOT
    manifest = json.loads((diagnostics / "processed_manifest.json").read_text())
    assert manifest["validation_passed"] is False
    audit = json.loads((diagnostics / "audit.json").read_text())
    assert audit["mismatches"] == (1 if failure == "audit_mismatch" else 0)
    assert audit["passed"] is (failure == "schema_rejection")
    assert (diagnostics / "issues.json").is_file()
    assert (accepted / "processed_manifest.json").read_text() == accepted_manifest


@pytest.mark.parametrize(
    "changed_file",
    ["src/macrolab/data/synthetic.py", "configs/supplemental_mappings.yaml", "uv.lock"],
)
def test_processing_fingerprint_detects_uncommitted_code_mapping_and_lock_changes(
    tmp_path: Path, changed_file: str
) -> None:
    concepts = inputs(tmp_path)
    original = pipeline.processing_inputs(tmp_path, concepts)
    (tmp_path / changed_file).write_text("# Changed without any git commit\n")

    changed = pipeline.processing_inputs(tmp_path, concepts)

    assert changed["fingerprint"] != original["fingerprint"]
    assert changed["files"][changed_file] != original["files"][changed_file]


def test_processing_fingerprint_tracks_definitions_but_not_generated_mapping_output(
    tmp_path: Path,
) -> None:
    concepts = inputs(tmp_path)
    original = pipeline.processing_inputs(tmp_path, concepts)
    concepts[0]["country_mappings"] = {"USA": {"source": "OECD"}}
    assert pipeline.processing_inputs(tmp_path, concepts) == original

    concepts[0]["default_transform"] = "difference"
    assert pipeline.processing_inputs(tmp_path, concepts)["fingerprint"] != original["fingerprint"]
