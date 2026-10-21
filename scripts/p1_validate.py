"""Verify isolated candidate data and template numerics against accepted local inputs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from macrolab.analysis.config import canonical_json, required_concepts, validated_config
from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/p1"
BASELINES = {
    "monetary_policy": "runs/g31/after.json",
    "taylor_rule": "runs/g21/after/taylor_rule.json",
    "phillips_curve": "runs/g21/after/phillips_curve.json",
    "okuns_law": "runs/g21/after/okuns_law.json",
}
EXCLUDED = {
    "checks",
    "code_version",
    "runtime_ms",
    "source_data_sha256",
    "prepared_inputs_sha256",
}


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def numerical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: numerical(item) for key, item in value.items() if key not in EXCLUDED}
    if isinstance(value, list):
        return [numerical(item) for item in value]
    return value


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def bundle(config: dict[str, Any], mode: str) -> dict[str, Any]:
    directory = OUTPUT / mode / "public/data/countries"
    result: dict[str, Any] = {
        "snapshot_id": config["snapshot_id"],
        "countries": {},
    }
    for country in config["countries"]:
        content = json.loads((directory / f"{country}.json").read_text())
        result["as_of_date"] = content["as_of_date"]
        cards = {card["concept_id"]: card for card in content["cards"]}
        result["countries"][country] = {
            "metadata": content["country"],
            "series": {
                cid: {"metadata": cards[cid], "observations": content["series"][cid]}
                for cid in required_concepts(config)
            },
        }
    return result


def main() -> None:
    report: dict[str, Any] = {"status": "in_progress", "templates": [], "data": {}}
    save(OUTPUT / "validation.json", report)
    protected = [
        ROOT / "data/processed/current/processed_manifest.json",
        ROOT / "web/public/data/manifest.json",
        ROOT / "runs/g4/model-validation.json",
        *[ROOT / name for name in BASELINES.values()],
    ]
    before_hashes = {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in protected}
    manifest = json.loads(protected[0].read_text())
    all_directory = OUTPUT / "all-local-only/public/data"
    cleared_directory = OUTPUT / "cleared/public/data"
    country_values, retained_values, profile_values, withheld_notes = 0, 0, 0, 0
    for source in sorted((ROOT / "data/processed/current/browser").glob("*.json")):
        if source.name == "global-variants.json":
            continue
        original = json.loads(source.read_text())
        all_data = json.loads((all_directory / "countries" / source.name).read_text())
        cleared = json.loads((cleared_directory / "countries" / source.name).read_text())
        if all_data["series"] != original["series"]:
            raise ValueError(f"All-source comparison changed accepted values: {source.name}")
        country_values += sum(len(series) for series in all_data["series"].values())
        for cid, series in cleared["series"].items():
            accepted = {str(row[0]): row for row in original["series"][cid]}
            if any(row != accepted.get(str(row[0])) for row in series):
                raise ValueError(f"Cleared candidate changed a retained value: {source.name}/{cid}")
            retained_values += len(series)
        original_profiles = {
            (row["profile_id"], row["date"]): row["value"] for row in original["profiles"]
        }
        for candidate in (all_data, cleared):
            if candidate["country"]["notes"]:
                raise ValueError("Unreviewed country notes entered a static candidate")
            withheld_notes += 1
            for row in candidate["profiles"]:
                if row["value"] != original_profiles[(row["profile_id"], row["date"])]:
                    raise ValueError("A retained profile value changed")
        profile_values += len(cleared["profiles"])
    report["data"] = {
        "snapshot_id": manifest["snapshot_id"],
        "all_series_observations_exact": country_values,
        "cleared_series_observations_exact": retained_values,
        "cleared_profile_observations_exact": profile_values,
        "country_bundles_with_notes_withheld": withheld_notes,
    }
    original_variants = json.loads(
        (ROOT / "data/processed/current/browser/global-variants.json").read_text()
    )["variants"]
    all_variants = json.loads((all_directory / "global-variants.json").read_text())["variants"]
    cleared_variants = json.loads((cleared_directory / "global-variants.json").read_text())[
        "variants"
    ]
    for name, variant in original_variants.items():
        if all_variants[name]["observations"] != variant["observations"]:
            raise ValueError("All-source comparison changed a global variant")
        accepted = {str(row[0]): row for row in variant["observations"]}
        if any(row != accepted.get(str(row[0])) for row in cleared_variants[name]["observations"]):
            raise ValueError("Cleared candidate changed a retained global-variant value")
    report["data"]["global_variant_observations_all"] = sum(
        len(variant["observations"]) for variant in all_variants.values()
    )
    report["data"]["global_variant_observations_cleared"] = sum(
        len(variant["observations"]) for variant in cleared_variants.values()
    )
    for directory in (all_directory, cleared_directory):
        for path in directory.rglob("*.json"):
            content = path.read_text()
            if any(token in content for token in ('"raw_path"', "data/raw/", '"audit"', str(ROOT))):
                raise ValueError(f"Private ingestion metadata entered a public file: {path.name}")
    for name, baseline_path in BASELINES.items():
        config = json.loads((ROOT / "configs/templates" / f"{name}.json").read_text())
        baseline = json.loads((ROOT / baseline_path).read_text())
        if validated_config(config) != baseline["config"]:
            raise ValueError(f"Original template configuration changed: {name}")
        accepted = run_analysis(config)
        candidate = run_analysis(config, bundle(config, "all-local-only"))
        cleared = run_analysis(config, bundle(config, "cleared"))
        for mode, result in (("all-local-only", candidate), ("cleared", cleared)):
            save(OUTPUT / mode / "results" / f"{name}.json", result)
        if accepted["status"] != "ok" or candidate["status"] != "ok":
            raise ValueError(f"An unchanged all-source template was blocked: {name}")
        old, new = numerical(accepted), numerical(candidate)
        if old != new:
            save(OUTPUT / "comparison-before.json", old)
            save(OUTPUT / "comparison-after.json", new)
            raise ValueError(f"Candidate altered template numerics or sample: {name}")
        core_keys = {
            "coefficients_table",
            "filtered_series",
            "irf",
            "fevd",
            "diagnostics",
            "actual_sample",
        }
        old_core = numerical(
            {key: value for key, value in baseline["results"][0].items() if key in core_keys}
        )
        new_core = numerical(
            {key: value for key, value in candidate["results"][0].items() if key in core_keys}
        )
        if old_core != new_core:
            raise ValueError(f"Core numerical output differs from accepted evidence: {name}")
        blocks = [check for check in cleared["checks"] if check["level"] == "block"]
        if cleared["status"] != "blocked" or not any(
            "not included in this publication candidate" in check["message"] for check in blocks
        ):
            raise ValueError(f"Excluded inputs did not produce an honest publication block: {name}")
        report["templates"].append(
            {
                "id": name,
                "baseline": baseline_path,
                "config_hash": candidate["config_hash"],
                "all_source_numerics_sample_and_sensitivity_exact": True,
                "accepted_core_output_exact": True,
                "payload_sha256": digest(canonical_json(new).encode()),
                "sample": candidate["results"][0]["actual_sample"],
                "cleared_status": cleared["status"],
                "cleared_blocks": blocks,
            }
        )
        print(
            f"Verified {name}: exact all-source numerics; honest cleared-source block", flush=True
        )
    after_hashes = {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in protected}
    if before_hashes != after_hashes:
        raise ValueError("Accepted snapshot or earlier evidence changed")
    report.update(
        status="passed",
        protected_files_sha256=after_hashes,
        excluded_comparison_keys=sorted(EXCLUDED),
        comparison_note=(
            "Exact mathematical output and samples, including full sensitivity variants, "
            "against a fresh accepted-input run. Core output additionally matches stored "
            "G4-verified native G3.1 monetary/G2.1 linear evidence. Metadata-dependent "
            "source/prepared fingerprints "
            "necessarily change because licence credits and publication status change; these "
            "hashes, checks, version and runtime are explicitly excluded."
        ),
    )
    save(OUTPUT / "validation.json", report)


if __name__ == "__main__":
    main()
