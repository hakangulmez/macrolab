"""Compare unchanged template settings against the frozen P1 full-data baseline."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from macrolab.analysis.config import required_concepts
from macrolab.analysis.engine import run_analysis

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/p2"
EXCLUDED = {
    "checks",
    "code_version",
    "runtime_ms",
    "source_data_sha256",
    "prepared_inputs_sha256",
    "snapshot_id",
    "config_hash",
}


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def hashes(paths: list[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def bundle(config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"snapshot_id": config["snapshot_id"], "countries": {}}
    for country in config["countries"]:
        data = json.loads((OUTPUT / "public/data/countries" / f"{country}.json").read_text())
        result["as_of_date"] = data["as_of_date"]
        cards = {card["concept_id"]: card for card in data["cards"]}
        result["countries"][country] = {
            "metadata": data["country"],
            "series": {
                cid: {"metadata": cards[cid], "observations": data["series"][cid]}
                for cid in required_concepts(config)
            },
        }
    return result


def differences(old: Any, new: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    numerical: list[dict[str, Any]] = []
    structural: list[dict[str, Any]] = []
    compared = 0

    def visit(a: Any, b: Any, path: str) -> None:
        nonlocal compared
        if (
            isinstance(a, (int, float))
            and not isinstance(a, bool)
            and isinstance(b, (int, float))
            and not isinstance(b, bool)
        ):
            if not math.isfinite(a) or not math.isfinite(b):
                raise ValueError("Comparison encountered a nonfinite result")
            compared += 1
            if a != b:
                numerical.append({"path": path, "before": a, "after": b, "difference": b - a})
        elif isinstance(a, dict) and isinstance(b, dict):
            ka, kb = set(a) - EXCLUDED, set(b) - EXCLUDED
            for key in sorted(ka | kb):
                if key not in ka or key not in kb:
                    structural.append(
                        {"path": f"{path}/{key}", "before": a.get(key), "after": b.get(key)}
                    )
                else:
                    visit(a[key], b[key], f"{path}/{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                structural.append({"path": path, "before_length": len(a), "after_length": len(b)})
            for index, (left, right) in enumerate(zip(a, b, strict=False)):
                visit(left, right, f"{path}/{index}")
        elif a != b:
            structural.append({"path": path, "before": a, "after": b})

    visit(old, new, "")
    return numerical, structural, compared


def summary(result: dict[str, Any]) -> dict[str, Any]:
    country = result["results"][0]
    sample = country["actual_sample"]
    row = {
        "status": result["status"],
        "sample": {
            key: sample[key]
            for key in (
                "start",
                "end",
                "nobs",
                "common_nobs",
                "dropped_periods",
                "frequency_conversion",
            )
        },
        "checks": country["checks"],
        "sensitivity": [
            {
                key: variant[key]
                for key in (
                    "variant_id",
                    "status",
                    "sample",
                    "metrics",
                    "checks",
                    "diagnostics",
                    "reason",
                )
                if key in variant
            }
            for variant in country["sensitivity"]["variants"]
        ],
        "coefficients": country.get("coefficients_table", []),
    }
    if "irf" in country:
        irf = country["irf"]
        row["resolved_shock_pp"] = irf["shock_size"]
        row["peaks"] = []
        for column, variable in enumerate(irf["variables"]):
            horizon = max(
                range(len(irf["values"])), key=lambda index: abs(irf["values"][index][column])
            )
            row["peaks"].append(
                {
                    "variable": variable,
                    "horizon": irf["periods"][horizon],
                    "value": irf["values"][horizon][column],
                    "lower": irf["lower"][horizon][column],
                    "upper": irf["upper"][horizon][column],
                }
            )
    return row


def main() -> None:
    report: dict[str, Any] = {"status": "in_progress", "templates": {}}
    save(OUTPUT / "validation.json", report)
    protected = [
        *sorted((ROOT / "runs/p1").rglob("*")),
        ROOT / "data/processed/current/processed_manifest.json",
        ROOT / "runs/g4/model-validation.json",
    ]
    protected_hashes = hashes(protected)
    manifest = json.loads((OUTPUT / "public/data/manifest.json").read_text())
    before_directory = ROOT / "runs/p1/all-local-only/public/data/countries"
    unchanged, new_brent, removed_index, original_brent, profiles = 0, 0, 0, 0, 0
    for path in sorted((OUTPUT / "public/data/countries").glob("*.json")):
        old = json.loads((before_directory / path.name).read_text())
        new = json.loads(path.read_text())
        for cid, values in old["series"].items():
            if cid == "oil_brent":
                original_brent += len(values)
                new_brent += len(new["series"][cid])
                card = next(card for card in new["cards"] if card["concept_id"] == cid)
                if card["sources"] != ["EIA"] or card["source_priority"] != ["EIA"]:
                    raise ValueError("The P2 Brent card does not consistently identify EIA")
            elif cid == "commod_idx":
                if new["series"][cid]:
                    raise ValueError("Excluded commodity-index observations entered P2")
                removed_index += len(values)
            else:
                if values != new["series"][cid]:
                    raise ValueError(f"P2 changed a non-Brent observation: {path.name}/{cid}")
                unchanged += len(values)

        def key(row: dict[str, Any]) -> tuple[Any, ...]:
            return row["profile_id"], row["date"], row["value"]

        if sorted(map(key, old["profiles"])) != sorted(map(key, new["profiles"])):
            raise ValueError("P2 changed a country profile value")
        profiles += len(new["profiles"])
    variants = json.loads((OUTPUT / "public/data/global-variants.json").read_text())["variants"]
    if any(variant["observations"] for variant in variants.values()):
        raise ValueError("An excluded commodity variant entered the P2 candidate")
    report.update(
        snapshot_id=manifest["snapshot_id"],
        parent_snapshot_id=manifest["parent_snapshot_id"],
        observation_comparison={
            "unchanged_non_brent_observations": unchanged,
            "unchanged_profile_observations": profiles,
            "former_brent_observations": original_brent,
            "new_eia_brent_observations": new_brent,
            "commodity_index_observations_removed": removed_index,
            "commodity_variant_observations_retained": 0,
        },
        source_overrides=manifest["publication"]["source_overrides"],
    )
    for template in manifest["templates"]:
        name, config = template["id"], template["config"]
        baseline_path = ROOT / "runs/p1/all-local-only/results" / f"{name}.json"
        baseline = json.loads(baseline_path.read_text())
        original_settings = {
            key: value for key, value in baseline["config"].items() if key != "snapshot_id"
        }
        current = run_analysis(config, bundle(config))
        current_settings = {
            key: value for key, value in current["config"].items() if key != "snapshot_id"
        }
        if original_settings != current_settings:
            raise ValueError(f"P2 changed template defaults or settings: {name}")
        save(OUTPUT / "results" / f"{name}.json", current)
        if current["status"] != "ok":
            raise ValueError(f"P2 template is blocked: {name}")
        numerical, structural, count = differences(baseline, current)
        if name != "monetary_policy" and (numerical or structural):
            save(
                OUTPUT / "differences" / f"{name}.json",
                {"numerical": numerical, "structural": structural},
            )
            raise ValueError(f"An unrelated template changed numerically: {name}")
        filename = OUTPUT / "differences" / f"{name}.json"
        save(filename, {"numerical": numerical, "structural": structural})
        before, after = summary(baseline), summary(current)
        sample_fields = {"start", "end", "nobs", "common_nobs", "dropped_periods"}
        if any(before["sample"][key] != after["sample"][key] for key in sample_fields):
            raise ValueError(f"P2 altered the estimation sample or its dropped periods: {name}")
        before_conversion = before["sample"]["frequency_conversion"]
        after_conversion = after["sample"]["frequency_conversion"]
        for cid in before_conversion:
            if any(
                before_conversion[cid][key] != after_conversion[cid][key]
                for key in ("from", "to", "method", "required_observations")
            ):
                raise ValueError(f"P2 changed a frequency conversion rule: {name}/{cid}")
        largest = max(numerical, key=lambda row: abs(row["difference"]), default=None)
        report["templates"][name] = {
            "baseline": str(baseline_path.relative_to(ROOT)),
            "settings_unchanged_except_snapshot": True,
            "same_sample_and_drop_accounting": True,
            "same_frequency_conversion_rules": True,
            "frequency_conversion_bookkeeping_changes": differences(
                before_conversion, after_conversion
            )[1],
            "numeric_leaves_compared": count,
            "numerical_differences": len(numerical),
            "structural_differences": len(structural),
            "maximum_absolute_difference": abs(largest["difference"]) if largest else 0,
            "maximum_difference_path": largest["path"] if largest else None,
            "full_differences": str(filename.relative_to(ROOT)),
            "before": before,
            "after": after,
        }
        print(
            f"{name}: {len(numerical)} numerical differences; sample/settings unchanged", flush=True
        )
        save(OUTPUT / "validation.json", report)
    if hashes(protected) != protected_hashes:
        raise ValueError("P1 outputs, accepted parent snapshot or G4 evidence changed")
    report.update(
        status="passed",
        protected_files_sha256=protected_hashes,
        excluded_comparison_fields=sorted(EXCLUDED),
        comparison_note=(
            "No estimator or template settings changed. Only monetary Brent data changed; "
            "three unrelated templates remain numerically exact. Source/config fingerprints "
            "change with the explicit candidate snapshot and licence metadata."
        ),
    )
    save(OUTPUT / "validation.json", report)


if __name__ == "__main__":
    main()
