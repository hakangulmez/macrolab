"""Explicit local-only refresh, immutable snapshots and comparison with a chosen baseline."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from g5_data import load as load_additions
from p1_prepare import Policy, filter_rows, read_policy, verified_file
from p2_eia import load as load_eia
from p2_validate import differences, summary

from macrolab.analysis.engine import run_analysis
from macrolab.data.correction import read_rows
from macrolab.data.pipeline import collect, publish, write_json
from macrolab.data.snapshot import SnapshotClient, SnapshotError, sha256_file, verify_raw_manifest
from macrolab.data.sources import eia
from macrolab.data.sources.v1 import fetch_v1

ROOT = Path(__file__).resolve().parents[1]


def cleared(rows: list[dict[str, Any]], policy: Policy) -> list[dict[str, Any]]:
    """Retain private raw audit pointers while applying reviewed public attribution."""
    allowed = [r for r in rows if all(d["status"] == "allowed" for d in policy.decisions(r))]
    public, _, _ = filter_rows(allowed, policy, "cleared")
    return [{**original, **processed} for original, processed in zip(allowed, public, strict=True)]


def accepted(root: Path, policy: Policy) -> dict[str, Any]:
    base = root / "data/processed/snapshots/20261021-0025"
    manifest = json.loads((base / "processed_manifest.json").read_text())
    if not manifest["validation_passed"]:
        raise SnapshotError("The accepted parent did not pass validation")
    for name in manifest["files"]:
        verified_file(base, manifest, name)
    countries = json.loads((base / "countries.json").read_text())
    rows = cleared(read_rows(base / "series.parquet"), policy)
    brent, _ = load_eia(root)
    rows += [{**row, "country": c["iso3"]} for c in countries for row in brent]
    return {
        "countries": countries,
        "rows": rows,
        "variant_rows": [],
        "profiles": cleared(read_rows(base / "profiles.parquet"), policy),
        "issues": [],
        "source_details": {"accepted_parent": manifest["snapshot_id"]},
        "prepared_selection": {"selected": rows, "losing": [], "selections": [], "issues": []},
    }


def fresh_eia(client: SnapshotClient, countries: list[dict[str, Any]]) -> dict[str, Any]:
    workbook = client.fetch(
        "EIA", "brent-monthly-xls", eia.WORKBOOK_URL, "application/vnd.ms-excel"
    )
    table = client.fetch("EIA", "brent-monthly-table", eia.TABLE_URL, "text/html")
    if (
        workbook.record.status != 200
        or table.record.status != 200
        or not workbook.body
        or not table.body
    ):
        raise SnapshotError("Required current EIA source or independent audit table unavailable")
    rows = eia.parse_workbook(workbook.body)
    values, release = eia.parse_table(table.body)
    audit = eia.audit(rows, values)
    output = []
    for row in rows:
        output.append(
            {
                **row,
                "country": "GLOBAL",
                "concept_id": "oil_brent",
                "source": "EIA",
                "source_series_id": eia.SERIES_ID,
                "source_url": eia.WORKBOOK_URL,
                "raw_path": workbook.record.raw_path,
                "freq": "M",
                "unit": "USD_PER_BARREL",
                "unit_mult": 0,
                "sa_flag": "NSA",
                "price_basis": "nominal",
                "base_year": None,
                "obs_status": "reported",
                "shared": True,
                "flags": [],
                "attribution": (
                    f"Source: U.S. Energy Information Administration, {eia.TITLE}; "
                    f"{eia.WORKBOOK_URL}; released {release}; "
                    f"accessed {workbook.record.retrieved_utc}. "
                    "Public domain; MacroLab transformations identified separately."
                ),
                "terms_status": "allowed: EIA public-domain data",
            }
        )
    return {"rows": output, "audit": audit}


class ClearedClient(SnapshotClient):
    """Reject unchecked source flows before requesting their observation payloads."""

    def __init__(self, root: Path, snapshot_id: str, policy: Policy, as_of: date):
        super().__init__(root, snapshot_id, as_of_date=as_of)
        self.policy = policy

    def fetch(self, source: str, probe_id: str, url: str, accept: str) -> Any:
        if "PinkSheet" in url or "commodity-markets" in url or "CMO-" in url:
            raise SnapshotError("Pink Sheet is excluded from refresh")
        if source in {"OECD", "IMF"} and "/data/" in url:
            allowed = [
                rule
                for rule in self.policy.rules
                if rule["source"] == source and rule["status"] == "allowed"
            ]
            if not any(
                url.startswith(prefix)
                for rule in allowed
                for prefix in rule.get("source_url_prefixes", [])
            ):
                raise SnapshotError(f"Flow has no reviewed redistribution clearance: {url}")
        result = super().fetch(source, probe_id, url, accept)
        if result.record.status != 200 or not result.body or not result.record.body_complete:
            raise SnapshotError(
                f"Source failed: {source}/{probe_id}; status={result.record.status}; "
                f"error={result.record.error}; url={url}"
            )
        return result


def changes(before: dict[str, list[Any]], after: dict[str, list[Any]]) -> list[dict[str, Any]]:
    output = []
    for key in sorted(set(before) | set(after)):
        old = {r[0]: float(r[1]) for r in before.get(key, [])}
        new = {r[0]: float(r[1]) for r in after.get(key, [])}
        revised = [p for p in old.keys() & new.keys() if old[p] != new[p]]
        material = [p for p in revised if abs(new[p] - old[p]) > max(1e-8, 1e-6 * abs(old[p]))]
        added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
        if added or removed or revised:
            output.append(
                {
                    "series": key,
                    "added": len(added),
                    "removed": len(removed),
                    "revised": len(revised),
                    "above_threshold": len(material),
                    "max_revision": max((abs(new[p] - old[p]) for p in revised), default=0),
                    "start": min(new, default=None),
                    "end": max(new, default=None),
                }
            )
    return output


def comparison_bundle(source: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Include the EA first stage and explicit variants for the two v1 templates."""
    countries = set(config["countries"])
    if config["model"]["id"] == "cmp.common_shock":
        countries.add("EA")
    bundle: dict[str, Any] = {"countries": {}}
    variant_file = (
        source.parent / "global-variants.json"
        if source.name == "countries"
        else source / "global-variants.json"
    )
    if variant_file.exists():
        bundle["variants"] = json.loads(variant_file.read_text())["variants"]
        for variant in bundle["variants"].values():
            observations = variant["observations"]
            if observations:
                variant["metadata"].setdefault("start", observations[0][0])
                variant["metadata"].setdefault("end", observations[-1][0])
    for country in sorted(countries):
        data = json.loads((source / f"{country}.json").read_text())
        cards = {c["concept_id"]: c for c in data["cards"]}
        bundle.update(snapshot_id=data["snapshot_id"], as_of_date=data["as_of_date"])
        bundle["countries"][country] = {
            "metadata": data["country"],
            "series": {
                cid: {"metadata": cards[cid], "observations": values}
                for cid, values in data["series"].items()
            },
        }
    return bundle


def refresh_summary(result: dict[str, Any]) -> dict[str, Any]:
    if result["config"]["model"]["id"] not in {"lp.ols", "cmp.common_shock"}:
        return summary(result)
    countries = result.get("results", [])
    return {
        "status": result["status"],
        "sample": countries[0].get("actual_sample", {}) if countries else {},
        "samples": {r["country"]: r.get("actual_sample", {}) for r in countries},
        "peaks": result.get("template_summary", []),
        "checks": result.get("checks", []),
        "sensitivity": result.get("template_sensitivity", []),
        "pass_through": countries[0].get("pass_through") if countries else None,
    }


def template_comparison(
    root: Path, previous: Path, destination: Path, snapshot: str
) -> dict[str, Any]:
    output = {}
    for file in sorted((root / "configs/templates").glob("*.json")):
        config = json.loads(file.read_text())
        results = []
        for source, sid in ((previous / "countries", None), (destination / "browser", snapshot)):
            selected = deepcopy(config)
            bundle = comparison_bundle(source, selected)
            selected["snapshot_id"] = sid or bundle["snapshot_id"]
            if selected["model"]["id"] == "cmp.common_shock":
                selected["model"]["params"]["first_stage"]["snapshot_id"] = selected["snapshot_id"]
            result = run_analysis(selected, bundle)
            results.append(result)
            write_json(
                root
                / "runs/refresh"
                / snapshot
                / "results"
                / f"{file.stem}-{'after' if sid else 'before'}.json",
                result,
            )
        delta, structural, count = differences(*results)
        output[file.stem] = {
            "before": refresh_summary(results[0]),
            "after": refresh_summary(results[1]),
            "numerical_fields": count,
            "changed_fields": len(delta),
            "maximum_absolute_difference": max((abs(d["difference"]) for d in delta), default=0),
            "structural_changes": structural,
        }
    return output


def resume_manifest(root: Path, snapshot: str) -> dict[str, Any]:
    """Resume only post-collection analysis; never fetch or rewrite immutable data."""
    marker = root / "data/manifests/refresh" / f"{snapshot}.json"
    destination = root / "data/processed/snapshots" / snapshot
    if not marker.exists() or json.loads(marker.read_text()).get("status") != "failed":
        raise SnapshotError("Resume requires a failed refresh marker")
    manifest = json.loads((destination / "processed_manifest.json").read_text())
    if not manifest["validation_passed"] or not manifest["audit_summary"]["passed"]:
        raise SnapshotError("Cannot resume a snapshot with failed data validation/audit")
    for name in manifest["files"]:
        verified_file(destination, manifest, name)
    verify_raw_manifest(root, snapshot)
    requests = [
        json.loads(line)
        for line in (root / "data/manifests/raw_manifest.jsonl").read_text().splitlines()
        if line.strip()
    ]
    requests = [r for r in requests if r["snapshot_id"] == snapshot]
    if not requests or any(r["status"] != 200 or not r["body_complete"] for r in requests):
        raise SnapshotError("Cannot resume after a source failure")
    return manifest


def run(
    root: Path, *, dry_run: bool, snapshot: str, previous: Path, resume_comparison: bool = False
) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8}-\d{4}", snapshot):
        raise SnapshotError("Snapshot must have the form YYYYMMDD-HHMM (UTC)")
    marker = root / "data/manifests/refresh" / f"{snapshot}.json"
    destination = root / "data/processed/snapshots" / snapshot
    if not resume_comparison and (marker.exists() or destination.exists()):
        raise SnapshotError("Immutable snapshot identifier already exists; choose a new minute")
    if not previous.resolve().is_relative_to(root.resolve()):
        raise SnapshotError("Comparison data must be inside this project")
    baseline = json.loads((previous / "manifest.json").read_text())
    as_of = date.fromisoformat(baseline["as_of_date"]) if dry_run else datetime.now(UTC).date()
    policy = Policy(read_policy(root / "configs/publication_sources_v1.json"))
    if resume_comparison:
        manifest = resume_manifest(root, snapshot)
        as_of = date.fromisoformat(manifest["as_of_date"])
    write_json(
        marker,
        {
            "snapshot_id": snapshot,
            "dry_run": dry_run,
            "status": "building",
            "as_of_date": as_of.isoformat(),
            "previous_snapshot": baseline["snapshot_id"],
            "publication_approved": False,
        },
    )
    try:
        if resume_comparison:
            collected = {"countries": json.loads((destination / "countries.json").read_text())}
        else:
            if dry_run:
                collected = accepted(root, policy)
                additions = load_additions(root)
            else:
                client = ClearedClient(root, snapshot, policy, as_of)
                collected = collect(
                    client, include_g11=True, cleared_only=True, fail_on_source_error=True
                )
                brent = fresh_eia(client, collected["countries"])
                collected["rows"].extend(brent["rows"])
                collected["source_details"]["EIA"] = brent["audit"]
                additions = fetch_v1(client, collected["countries"], as_of)
            collected["rows"].extend(additions["rows"])
            collected["variant_rows"] = additions["variant_rows"]
            collected["source_details"]["v1"] = additions["audit"]
            for key in ("rows", "variant_rows", "profiles"):
                collected[key] = cleared(collected[key], policy)
            if dry_run:
                collected["prepared_selection"]["selected"] = collected["rows"]
            concepts = yaml.safe_load((root / "configs/indicators.yaml").read_text())["concepts"]
            for concept in concepts:
                if concept["concept_id"] == "oil_brent":
                    concept["source_priority"] = ["EIA"]
                if concept["concept_id"] == "commod_idx":
                    concept.update(source_priority=["IMF"], default_transform="yoy_pct")
            rules = yaml.safe_load((root / "configs/data_rules.yaml").read_text())
            rules["as_of_date"] = as_of.isoformat()
            manifest = publish(
                root, snapshot, collected, concepts, rules, as_of, offline=dry_run, promote=False
            )
        series_changes, newly_stale = [], []
        for country in collected["countries"]:
            iso3 = country["iso3"]
            old_path = previous / "countries" / f"{iso3}.json"
            old = (
                json.loads(old_path.read_text())
                if old_path.exists()
                else {"series": {}, "cards": []}
            )
            new = json.loads((destination / "browser" / f"{iso3}.json").read_text())
            series_changes.extend(
                {"country": iso3, **item} for item in changes(old["series"], new["series"])
            )
            was_stale = {
                c["concept_id"] for c in old["cards"] if "stale" in c.get("reason_codes", [])
            }
            newly_stale.extend(
                f"{iso3}/{c['concept_id']}"
                for c in new["cards"]
                if "stale" in c.get("reason_codes", []) and c["concept_id"] not in was_stale
            )
        templates = template_comparison(root, previous, destination, snapshot)
        report = {
            "snapshot_id": snapshot,
            "dry_run": dry_run,
            "as_of_date": as_of.isoformat(),
            "previous_snapshot": baseline["snapshot_id"],
            "manifest": manifest,
            "series_changes": series_changes,
            "newly_stale": newly_stale,
            "templates": templates,
            "passed": manifest["validation_passed"]
            and all(t["after"]["status"] == "ok" for t in templates.values()),
        }
        if dry_run and any(t["changed_fields"] for t in templates.values()):
            report["passed"] = False
        evidence = root / "runs/refresh" / snapshot / "comparison.json"
        write_json(evidence, report)
        mode = "offline accepted P2 + G5 additions" if dry_run else "live cleared-source fetch"
        rows = [
            f"# Refresh {snapshot}",
            "",
            f"Mode: {mode}. Previous: `{baseline['snapshot_id']}`. As of: {as_of}.",
            "",
            "No publication, deployment or local current-pointer change. "
            "Snapshot and raw responses are immutable. No Pink Sheet or FRED requests. "
            "Country narratives withheld.",
            "",
            f"Full audit: {manifest['audit_summary']}. Additional variant audit: 18 exact checks. "
            f"Passed: {report['passed']}.",
            "",
            "Every changed concept/country is listed below. A material revision exceeds "
            "max(1e-8 source units, 1e-6 × absolute old value); added/removed periods are "
            "counted separately. No observation levels are embedded in this report.",
            "",
            "| Country | Concept | Added | Removed | Revised | Above threshold | "
            "Maximum revision | Start | End |",
            "|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
        rows += [
            f"| {r['country']} | {r['series']} | {r['added']} | {r['removed']} | {r['revised']} | "
            f"{r['above_threshold']} | {r['max_revision']:.8g} | {r['start']} | {r['end']} |"
            for r in series_changes
        ]
        rows += [
            "",
            f"Newly stale: {', '.join(newly_stale) or 'none'}.",
            "",
            "| Template | Before sample | After sample | Numerical fields | "
            "Changed | Maximum absolute difference |",
            "|---|---|---|---:|---:|---:|",
        ]
        for name, item in templates.items():
            a, b = item["before"]["sample"], item["after"]["sample"]
            rows.append(
                f"| {name} | {a['start']}–{a['end']} (n={a['nobs']}) | "
                f"{b['start']}–{b['end']} (n={b['nobs']}) | {item['numerical_fields']} | "
                f"{item['changed_fields']} | {item['maximum_absolute_difference']:.8g} |"
            )
        counts = Counter(
            c["status"] for c in json.loads((destination / "series_cards.json").read_text())
        )
        rows += [
            "",
            f"Coverage: {dict(counts)}. Detailed warnings and every template result are in ignored "
            f"`{evidence.relative_to(root)}`; coverage and audit evidence are in "
            f"`{destination.relative_to(root)}`.",
            "",
            "Processed manifest SHA-256: "
            f"`{sha256_file(destination / 'processed_manifest.json')}`.",
        ]
        (root / "docs" / f"REFRESH_{snapshot}.md").write_text("\n".join(rows) + "\n")
        write_json(
            marker,
            {
                "snapshot_id": snapshot,
                "dry_run": dry_run,
                "status": "passed" if report["passed"] else "failed",
                "destination": str(destination.relative_to(root)),
                "report": f"docs/REFRESH_{snapshot}.md",
                "publication_approved": False,
            },
        )
        if not report["passed"]:
            raise SnapshotError(
                "Refresh failed; retained diagnostic artifacts, no pointer promotion"
            )
        return report
    except Exception as exc:
        write_json(
            marker,
            {
                "snapshot_id": snapshot,
                "dry_run": dry_run,
                "status": "failed",
                "error": str(exc),
                "publication_approved": False,
            },
        )
        report_path = root / "docs" / f"REFRESH_{snapshot}.md"
        if not report_path.exists():
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                f"# Refresh {snapshot} — stopped\n\n"
                f"Previous accepted snapshot: `{baseline['snapshot_id']}`. "
                f"Requested as-of date: {as_of}.\n\n"
                f"**Failed:** {exc}\n\n"
                "Stopped under the G9 source-failure rule. No incomplete snapshot was "
                "promoted or used for a release candidate. Raw attempt evidence and the "
                "failed marker are retained; the accepted snapshot is unchanged.\n\n"
                "Changed series, material revisions, new stale flags and all six template "
                "comparisons are not available because collection did not complete. "
                "No conclusion about unchanged licences can be drawn from this failed run.\n"
            )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--snapshot", default=datetime.now(UTC).strftime("%Y%m%d-%H%M"))
    parser.add_argument("--previous", type=Path, default=ROOT / "runs/p2/public/data")
    parser.add_argument("--resume-comparison", action="store_true")
    args = parser.parse_args()
    report = run(
        ROOT,
        dry_run=args.dry_run,
        snapshot=args.snapshot,
        previous=args.previous,
        resume_comparison=args.resume_comparison,
    )
    write_json(
        ROOT / "runs/refresh" / report["snapshot_id"] / "result.json",
        {
            "snapshot_id": report["snapshot_id"],
            "passed": report["passed"],
            "manifest": report["manifest"],
        },
    )
    print(json.dumps({"snapshot_id": report["snapshot_id"], "passed": report["passed"]}))


if __name__ == "__main__":
    main()
