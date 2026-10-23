"""Prepare a separate, policy-filtered static candidate from accepted local inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pyarrow.parquet as pq
import yaml

from macrolab.data.coverage import build_coverage
from macrolab.export.script import DEPENDENCIES
from macrolab.models.registry import catalogue

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"allowed", "unclear", "not_allowed"}
SEGMENT_FIELDS = (
    "concept_id",
    "source",
    "source_series_id",
    "source_url",
    "attribution",
    "terms_status",
    "unit",
    "unit_mult",
    "sa_flag",
    "price_basis",
    "base_year",
    "freq",
    "shared",
    "source_geo",
    "variant",
    "source_unit",
    "unit_label",
    "definition",
    "source_adjustment",
    "source_price_base",
    "source_country",
    "aggregation",
)
ROW_FIELDS = set(SEGMENT_FIELDS) | {
    "country",
    "date",
    "value",
    "obs_status",
    "flags",
    "profile_id",
    "indicator_title",
    "publication_restrictions",
    "terms_urls",
}
COUNTRY_FIELDS = {
    "iso3",
    "iso2",
    "name",
    "region",
    "oecd_region",
    "oecd_region_code",
    "group",
    "membership_group",
    "membership_source_url",
    "membership_metadata_version",
    "currency",
    "currency_code",
    "currency_source_url",
    "eu_member",
    "euro_adoption",
    "euro_adoption_source_url",
    "euro_adoption_sources",
    "monetary_union",
    "policy_rate_shared",
    "default_shock_sample_start",
}
PACKAGE_NOTICES = {
    "react": ["LICENSE"],
    "react-dom": ["LICENSE"],
    "scheduler": ["LICENSE"],
    "echarts": ["LICENSE", "NOTICE", "licenses/LICENSE-d3"],
    "zrender": ["LICENSE"],
    "tslib": ["LICENSE.txt", "CopyrightNotice.txt"],
    "ajv": ["LICENSE"],
    "fflate": ["LICENSE"],
    "fast-deep-equal": ["LICENSE"],
    "fast-uri": ["LICENSE"],
    "json-schema-traverse": ["LICENSE"],
    "require-from-string": ["license"],
    "@fontsource/inter": ["LICENSE"],
    "@fontsource/ibm-plex-mono": ["LICENSE"],
}


def encoded(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded(value) + b"\n")


def read_policy(path: Path) -> dict[str, Any]:
    policy = json.loads(path.read_text())
    if policy.get("schema_version") != 1 or policy.get("publication_approved") is not False:
        raise ValueError("P1 requires a version-one policy that retains publication approval")
    rules = policy.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("Publication policy needs explicit dataset rules")
    ids = set()
    for rule in rules:
        if not all(
            isinstance(rule.get(key), str) and rule[key] for key in ("id", "source", "dataset")
        ):
            raise ValueError("Each policy rule needs an id, source and dataset")
        if rule.get("status") not in STATUSES or rule["id"] in ids:
            raise ValueError("Policy statuses must be explicit and rule IDs unique")
        ids.add(rule["id"])
        for key in ("series_id_prefixes", "source_url_prefixes"):
            if key in rule and (
                not isinstance(rule[key], list)
                or not rule[key]
                or any(not isinstance(v, str) or not v for v in rule[key])
            ):
                raise ValueError("Policy selectors must be nonempty lists of strings")
    return policy


def worldbank_dataset(row: dict[str, Any]) -> str | None:
    if str(row.get("source_series_id", "")).startswith("PinkSheet/"):
        return "worldbank_pink_sheet"
    parsed = urlparse(str(row.get("source_url", "")))
    if (
        parsed.hostname == "api.worldbank.org"
        and parse_qs(parsed.query).get("source") == ["2"]
        and "/indicator/" in parsed.path
    ):
        return "worldbank_wdi"
    return None


class Policy:
    """Fail closed on unmatched/ambiguous datasets and unprovable derivations."""

    def __init__(self, policy: dict[str, Any]):
        self.rules = policy["rules"]
        self.by_id = {rule["id"]: rule for rule in self.rules}
        self.cache: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    def decisions(self, row: dict[str, Any], depth: int = 0) -> list[dict[str, Any]]:
        source = str(row.get("source") or "Unknown")
        audit = row.get("audit") or {}
        if isinstance(audit, str):
            audit = json.loads(audit)
        if not isinstance(audit, dict):
            return [self.unknown(source, "Unverifiable observation provenance")]
        if source == "Derived" or "components" in audit:
            components = audit.get("components")
            if (
                depth >= 12
                or not isinstance(components, list)
                or not components
                or any(not isinstance(v, dict) for v in components)
            ):
                return [self.unknown(source, "Derived value lacks complete component provenance")]
            decisions = [
                item for component in components for item in self.decisions(component, depth + 1)
            ]
            return list({item["id"]: item for item in decisions}.values())
        key = (source, str(row.get("source_series_id") or ""), str(row.get("source_url") or ""))
        if key in self.cache:
            return self.cache[key]
        matched = []
        for rule in self.rules:
            if rule["source"] != source or not key[1] or not key[2].startswith("https://"):
                continue
            if source == "WorldBank" and rule["id"] != worldbank_dataset(row):
                continue
            if rule["id"] == "worldbank_wdi" and key[1] not in rule.get(
                "attribution_by_series", {}
            ):
                continue
            if any(
                name in rule and not any(value.startswith(prefix) for prefix in rule[name])
                for name, value in (("series_id_prefixes", key[1]), ("source_url_prefixes", key[2]))
            ):
                continue
            matched.append(rule)
        if len(matched) != 1:
            result = [
                self.unknown(source, "No unique approved dataset policy matches this observation")
            ]
        else:
            result = [self.public_decision(matched[0])]
        self.cache[key] = result
        return result

    @staticmethod
    def public_decision(rule: dict[str, Any]) -> dict[str, Any]:
        reason = rule.get("decision_required")
        if not isinstance(reason, str):
            restrictions = rule.get("restrictions")
            reason = "; ".join(restrictions) if isinstance(restrictions, list) else restrictions
        return {
            "id": rule["id"],
            "source": rule["source"],
            "dataset": rule["dataset"],
            "status": rule["status"],
            "reason": reason or "Dataset policy decision",
        }

    @staticmethod
    def unknown(source: str, reason: str) -> dict[str, Any]:
        return {
            "id": f"unmatched:{source}",
            "source": source,
            "dataset": "unresolved",
            "status": "unclear",
            "reason": reason,
        }


def filter_rows(
    rows: Iterable[dict[str, Any]], policy: Policy, mode: str
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    if mode not in {"cleared", "all"}:
        raise ValueError("Source mode must be cleared or all")
    kept, cells, accounting = [], {}, {}
    for row in rows:
        decisions = policy.decisions(row)
        allowed = all(item["status"] == "allowed" for item in decisions)
        retained = mode == "all" or allowed
        ids = sorted(item["id"] for item in decisions)
        bucket = ("Derived:" if row.get("source") == "Derived" else "") + "+".join(ids)
        stats = accounting.setdefault(
            bucket,
            {
                "source": row.get("source"),
                "dataset_rules": ids,
                "input_observations": 0,
                "retained_observations": 0,
                "excluded_observations": 0,
                "value_payload_bytes": 0,
            },
        )
        stats["input_observations"] += 1
        stats["retained_observations" if retained else "excluded_observations"] += 1
        key = (
            str(row.get("country", "GLOBAL")),
            str(row.get("concept_id") or row.get("profile_id") or row.get("variant")),
        )
        cell = cells.setdefault(
            key, {"retained_observations": 0, "excluded_observations": 0, "excluded_sources": {}}
        )
        cell["retained_observations" if retained else "excluded_observations"] += 1
        if not allowed:
            cell["excluded_sources"].update(
                {d["id"]: d for d in decisions if d["status"] != "allowed"}
            )
        if retained:
            item = {key: value for key, value in row.items() if key in ROW_FIELDS}
            flags = item.get("flags", [])
            if isinstance(flags, str):
                flags = json.loads(flags)
            if not isinstance(flags, list) or any(not isinstance(v, str) for v in flags):
                raise ValueError("Stored observation flags must be a list of strings")
            item["flags"] = flags
            item["terms_status"] = (
                "allowed by reviewed dataset policy; publication approval pending"
                if allowed
                else "local-only comparison: dataset not cleared for publication"
            )
            credits = [str(item.get("attribution") or "")]
            restrictions, terms_urls = [], []
            for decision in decisions:
                rule = policy.by_id.get(decision["id"], {})
                credits.extend(citations(rule, row))
                restriction = rule.get("restrictions", [])
                restrictions.extend(restriction if isinstance(restriction, list) else [restriction])
                if rule.get("terms_url"):
                    terms_urls.append(rule["terms_url"])
                if rule.get("id") == "worldbank_wdi":
                    terms_urls.append("https://creativecommons.org/licenses/by/4.0/")
            item["attribution"] = "; ".join(dict.fromkeys(credit for credit in credits if credit))
            item["publication_restrictions"] = list(dict.fromkeys(restrictions))
            item["terms_urls"] = list(dict.fromkeys(terms_urls))
            item["_publication_bucket"] = bucket
            item["_publication_rule_ids"] = ids
            kept.append(item)
    return kept, cells, accounting


def citations(rule: dict[str, Any], row: dict[str, Any]) -> list[str]:
    """Resolve exact database citations, including each derived component's flow."""
    audit = row.get("audit") or {}
    if isinstance(audit, str):
        audit = json.loads(audit)
    if isinstance(audit, dict) and isinstance(audit.get("components"), list):
        return list(
            dict.fromkeys(
                credit for component in audit["components"] for credit in citations(rule, component)
            )
        )
    if row.get("source") != rule.get("source"):
        return []
    series = str(row.get("source_series_id", ""))
    exact = rule.get("attribution_by_series", {}).get(series)
    if exact:
        return [exact]
    for prefix, credit in sorted(
        rule.get("attribution_by_series_prefix", {}).items(), key=lambda item: -len(item[0])
    ):
        if series.startswith(prefix):
            return [credit]
    path = unquote(urlparse(str(row.get("source_url", ""))).path)
    flow = path.split("/data/", 1)[-1].split("/", 1)[0] if "/data/" in path else ""
    return [rule.get("attribution_by_flow", {}).get(flow, rule.get("attribution", ""))]


def read_rows(path: Path) -> Iterable[dict[str, Any]]:
    parquet = pq.ParquetFile(path)
    columns = sorted((ROW_FIELDS | {"audit"}) & set(parquet.schema_arrow.names))
    for batch in parquet.iter_batches(batch_size=4096, columns=columns):
        yield from batch.to_pylist()


def verified_file(directory: Path, snapshot: dict[str, Any], name: str) -> Path:
    path = directory / name
    expected = snapshot["files"].get(name)
    if not expected or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError(f"Unverified accepted input path: {name}")
    payload = path.read_bytes()
    if len(payload) != expected["bytes"] or digest(payload) != expected["sha256"]:
        raise ValueError(f"Accepted input checksum mismatch: {name}")
    return path


def safe_country(country: dict[str, Any]) -> dict[str, Any]:
    result = {key: deepcopy(value) for key, value in country.items() if key in COUNTRY_FIELDS}
    result.update(notes=[], notes_status="withheld_pending_review", notes_review_required=True)
    return result


def record_bytes(row: dict[str, Any], value: Any, accounting: dict[str, dict[str, Any]]) -> Any:
    accounting[row["_publication_bucket"]]["value_payload_bytes"] += len(encoded(value))
    return value


def compact(row: dict[str, Any], accounting: dict[str, dict[str, Any]]) -> list[Any]:
    return record_bytes(
        row, [row["date"], row["value"], row["obs_status"], row["flags"]], accounting
    )


def public_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key in ROW_FIELDS}


def copy_software_notices(root: Path, public: Path, lock: dict[str, Any]) -> dict[str, Any]:
    """Copy installed notices verbatim; make unresolved runtime notices explicit."""
    files = []
    packages = []

    def copy_notice(source: Path, destination: Path) -> None:
        content = source.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        files.append(
            {
                "path": str(destination.relative_to(public)),
                "bytes": len(content),
                "sha256": digest(content),
            }
        )

    copy_notice(root / "LICENSE", public / "licences/MacroLab/LICENSE")
    for name, notices in PACKAGE_NOTICES.items():
        directory = root / "web/node_modules" / name
        package = json.loads((directory / "package.json").read_text())
        packages.append(
            {"name": name, "version": package["version"], "license": package.get("license")}
        )
        for notice in notices:
            copy_notice(directory / notice, public / "licences" / name / notice)
    wheels = []
    for entry in lock["packages"].values():
        archive = public / "runtime/pyodide" / entry["file_name"]
        with zipfile.ZipFile(archive) as wheel:
            embedded = [
                name
                for name in wheel.namelist()
                if not name.endswith("/")
                and any(word in name.lower() for word in ("license", "licence", "notice"))
            ]
        wheels.append({"file_name": entry["file_name"], "embedded_notice_paths": embedded})
    result = {
        "schema_version": 1,
        "publication_approved": False,
        "status": "incomplete_pending_runtime_notice_review",
        "files": files,
        "packages": packages,
        "unchanged_runtime_wheels": wheels,
        "unresolved": [
            {
                "component": "Pyodide and bundled CPython runtime",
                "version": lock["pyodide_version"],
                "reason": (
                    "Complete runtime licence and copyright notices were not present in the "
                    "approved local cache. Wheel notices remain embedded in unchanged archives. "
                    "This publication item requires review before deployment; no new downloads "
                    "were made and these links do not substitute for the missing notices."
                ),
                "reference_urls": [
                    "https://github.com/pyodide/pyodide/blob/main/LICENSE",
                    "https://docs.python.org/3/license.html",
                ],
            }
        ],
    }
    write_json(public / "licences/manifest.json", result)
    return result


def prepare(
    root: Path = ROOT,
    *,
    mode: str = "cleared",
    base_path: str = "/macrolab/",
    candidate: str = "p1",
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    if mode not in {"cleared", "all"} or not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*", base_path):
        raise ValueError("Choose cleared/all sources and a simple absolute project base path")
    if candidate not in {"p1", "p2", "g9"} or (candidate in {"p2", "g9"} and mode != "cleared"):
        raise ValueError("P2 always applies the reviewed source policy; P1 all remains separate")
    policy_path = root / (
        "configs/publication_sources_v1.json"
        if candidate == "g9"
        else "configs/publication_sources.json"
    )
    policy_data = read_policy(policy_path)
    policy = Policy(policy_data)
    if candidate == "g9" and (not snapshot_id or not re.fullmatch(r"\d{8}-\d{4}", snapshot_id)):
        raise ValueError("G9 needs an explicit audited snapshot identifier")
    directory = (
        root / "data/processed/snapshots" / snapshot_id
        if candidate == "g9" and snapshot_id
        else root / "data/processed/current"
    )
    snapshot_bytes = (directory / "processed_manifest.json").read_bytes()
    snapshot = json.loads(snapshot_bytes)
    if not snapshot.get("validation_passed") or not snapshot.get("audit_summary", {}).get("passed"):
        raise ValueError("P1 only reads an accepted, audited local snapshot")
    target = (
        root / "runs" / candidate
        if candidate in {"p2", "g9"}
        else root / "runs/p1" / ("cleared" if mode == "cleared" else "all-local-only")
    )
    public = target / "public"
    if public.is_symlink() or not public.resolve().is_relative_to(
        (root / "runs" / candidate).resolve()
    ):
        raise ValueError("Candidate inputs must remain in the dedicated ignored P1 directory")
    if public.exists():
        shutil.rmtree(public)
    public.mkdir(parents=True)
    data = public / "data"
    originals = []
    for name in sorted(snapshot["files"]):
        if (
            name.startswith("browser/")
            and name.endswith(".json")
            and name != "browser/global-variants.json"
        ):
            originals.append(json.loads(verified_file(directory, snapshot, name).read_text()))
    countries = [safe_country(bundle["country"]) for bundle in originals]
    if len(countries) != snapshot["countries"]:
        raise ValueError("Country inventory differs from the accepted snapshot")
    rows, cells, accounting = filter_rows(
        read_rows(verified_file(directory, snapshot, "series.parquet")), policy, mode
    )
    eia_marker = None
    candidate_snapshot = snapshot["snapshot_id"]
    if candidate == "p2":
        from p2_eia import load as load_eia

        eia_rows, eia_marker = load_eia(root)
        stamp = eia_marker["snapshot_id"].removeprefix("p2-eia-").split("-")
        candidate_snapshot = f"{stamp[0]}-p2-eia-{stamp[1]}"
        if any(row["concept_id"] in {"oil_brent", "commod_idx"} for row in rows):
            raise ValueError("P2 requires the old Pink Sheet factors to be excluded by policy")
        additional, new_cells, new_accounting = filter_rows(
            ({**row, "country": country["iso3"]} for country in countries for row in eia_rows),
            policy,
            mode,
        )
        if len(additional) != len(eia_rows) * len(countries):
            raise ValueError("P2 EIA source is not cleared by the exact reviewed policy")
        rows.extend(additional)
        for key, cell in new_cells.items():
            original = cells[key]
            original["replaced_observations"] = original["excluded_observations"]
            original["retained_observations"] += cell["retained_observations"]
        accounting.update(new_accounting)
    profiles, profile_cells, profile_accounting = filter_rows(
        read_rows(verified_file(directory, snapshot, "profiles.parquet")), policy, mode
    )
    variants, variant_cells, variant_accounting = filter_rows(
        read_rows(verified_file(directory, snapshot, "variant_series.parquet")), policy, mode
    )
    definitions = yaml.safe_load((root / "configs/indicators.yaml").read_text())
    if candidate in {"p2", "g9"}:
        brent = next(item for item in definitions["concepts"] if item["concept_id"] == "oil_brent")
        brent["source_priority"] = ["EIA"]
        brent["title"] = "Europe Brent spot price (EIA), USD/bbl"
    if candidate == "g9":
        commodity = next(
            item for item in definitions["concepts"] if item["concept_id"] == "commod_idx"
        )
        commodity.update(
            source_priority=["IMF"],
            title="Primary commodity price index (IMF, non-fuel)",
            default_transform="yoy_pct",
        )
    rules = yaml.safe_load((root / "configs/data_rules.yaml").read_text())
    coverage, cards = build_coverage(
        rows,
        countries,
        definitions["concepts"],
        rules,
        date.fromisoformat(snapshot["as_of_date"]),
        [],
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["country"], row["concept_id"])].append(row)
    card_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card, cell_coverage in zip(cards, coverage, strict=True):
        details = cells.get(
            (card["country"], card["concept_id"]),
            {"retained_observations": 0, "excluded_observations": 0, "excluded_sources": {}},
        )
        details = {**details, "excluded_sources": list(details["excluded_sources"].values())}
        excluded = details["excluded_observations"]
        details["reason"] = (
            "Observations from uncleared datasets are excluded; "
            "no replacement data or defaults were substituted."
            if excluded
            else "No observations excluded by the selected source mode."
        )
        replacement = bool(details.get("replaced_observations"))
        if replacement:
            details["reason"] = (
                "The former Pink Sheet Brent observations are replaced by audited official EIA "
                "monthly Brent data for this P2 candidate. The accepted parent remains unchanged."
            )
        card["publication"] = details
        for segment in card["source_segments"]:
            sample_row = next(
                row
                for row in grouped[(card["country"], card["concept_id"])]
                if row["source"] == segment["source"]
                and row["source_series_id"] == segment["source_series_id"]
            )
            segment["publication_restrictions"] = sample_row["publication_restrictions"]
            segment["terms_urls"] = sample_row["terms_urls"]
            segment["publication_rule_ids"] = sample_row["_publication_rule_ids"]
            segment["snapshot_as_of"] = snapshot["as_of_date"]
        card["notes_status"] = "withheld_pending_review"
        if excluded and not replacement:
            for item in (card, cell_coverage):
                item["status"] = "limited" if details["retained_observations"] else "missing"
                item["reason_code"] = "publication_source_excluded"
                item["reason_codes"] = sorted(
                    set(item["reason_codes"] + ["publication_source_excluded"])
                )
                item["flags"] = sorted(set(item["flags"] + ["publication_source_excluded"]))
            card["warnings"] = sorted(set(card["warnings"] + ["publication_source_excluded"]))
        card_groups[card["country"]].append(card)
    country_files = {}
    for country in countries:
        iso3 = country["iso3"]
        selected_profiles = [row for row in profiles if row["country"] == iso3]
        rendered_profiles = [
            record_bytes(row, public_profile(row), profile_accounting) for row in selected_profiles
        ]
        latest = {}
        for row in selected_profiles:
            if row["profile_id"] not in latest or row["date"] > latest[row["profile_id"]]["date"]:
                latest[row["profile_id"]] = row
        country["latest_profiles"] = [
            record_bytes(row, public_profile(row), profile_accounting) for row in latest.values()
        ]
        country["coverage_counts"] = dict(Counter(card["status"] for card in card_groups[iso3]))
        country["profile_publication"] = {
            key[1]: {**item, "excluded_sources": list(item["excluded_sources"].values())}
            for key, item in profile_cells.items()
            if key[0] == iso3
        }
        bundle = {
            "snapshot_id": candidate_snapshot,
            "parent_snapshot_id": snapshot["snapshot_id"],
            "as_of_date": snapshot["as_of_date"],
            "country": {key: value for key, value in country.items() if key != "latest_profiles"},
            "cards": card_groups[iso3],
            "series": {
                concept["concept_id"]: [
                    compact(row, accounting) for row in grouped[(iso3, concept["concept_id"])]
                ]
                for concept in definitions["concepts"]
            },
            "profiles": rendered_profiles,
            "global_variants_ref": "global-variants.json",
            "publication_approved": False,
        }
        path = data / "countries" / f"{iso3}.json"
        write_json(path, bundle)
        country_files[iso3] = {
            "url": f"data/countries/{iso3}.json",
            "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes()),
        }
    variant_output = {}
    original_variants = json.loads(
        verified_file(directory, snapshot, "browser/global-variants.json").read_text()
    )
    for name, prior in original_variants["variants"].items():
        values = [row for row in variants if row.get("variant") == name]
        metadata = (
            {
                key: values[0].get(key)
                for key in (*SEGMENT_FIELDS, "publication_restrictions", "terms_urls")
            }
            if values
            else {key: value for key, value in prior["metadata"].items() if key in SEGMENT_FIELDS}
        )
        metadata["snapshot_as_of"] = snapshot["as_of_date"]
        variant_output[name] = {
            "metadata": metadata,
            "observations": [compact(row, variant_accounting) for row in values],
            "publication": {
                "status": "retained" if values else "excluded",
                "reason": "Dataset policy applies to global variants as well as default factors.",
            },
        }
    write_json(
        data / "global-variants.json",
        {
            "snapshot_id": candidate_snapshot,
            "variants": variant_output,
            "publication_approved": False,
        },
    )
    common = runpy.run_path(str(ROOT / "scripts/g3_prepare.py"))
    indicators = [
        {key: value for key, value in concept.items() if key != "country_mappings"}
        for concept in definitions["concepts"]
    ]
    for indicator in indicators:
        indicator["category"] = next(
            name for name, ids in common["CATEGORIES"].items() if indicator["concept_id"] in ids
        )
        indicator["frequency"] = indicator["native_frequency"]
        if candidate == "p2":
            indicator["publication"] = {"included": indicator["concept_id"] != "commod_idx"}
    templates = []
    for key, (title, description) in common["TEMPLATES"].items():
        config = json.loads((root / f"configs/templates/{key}.json").read_text())
        if candidate in {"p2", "g9"}:
            config["snapshot_id"] = candidate_snapshot
        missing = [
            {"country": country, "concept_id": spec["concept_id"]}
            for country in config["countries"]
            for spec in config["series"]
            if not grouped.get((country, spec["concept_id"]))
        ]
        templates.append(
            {
                "id": key,
                "title": title,
                "description": description,
                "config": config,
                "publication": {
                    "status": "blocked" if missing else "inputs_present",
                    "missing_series": missing,
                },
            }
        )
    from build_runtime_assets import build_wheel

    wheel = build_wheel(target / "runtime-build")
    runtime = public / "runtime"
    lock = json.loads((root / "web/runtime/assets.lock.json").read_text())
    runtime_entries = {name: entry for name, entry in lock["runtime_files"].items()}
    runtime_entries.update({entry["file_name"]: entry for entry in lock["packages"].values()})
    for name, entry in runtime_entries.items():
        source = root / ".cache/pyodide" / lock["pyodide_version"] / name
        payload = source.read_bytes()
        if digest(payload) != entry["sha256"] or (
            "bytes" in entry and len(payload) != entry["bytes"]
        ):
            raise ValueError(f"Cached pinned runtime checksum mismatch: {name}")
        (runtime / "pyodide").mkdir(parents=True, exist_ok=True)
        (runtime / "pyodide" / name).write_bytes(payload)
    shutil.copyfile(target / "runtime-build" / wheel["wheel_file"], runtime / wheel["wheel_file"])
    shutil.copyfile(root / "web/runtime/worker.mjs", runtime / "worker.mjs")
    shutil.copyfile(root / "web/runtime/assets.lock.json", runtime / "assets.lock.json")
    software_notices = copy_software_notices(root, public, lock)
    if candidate in {"p2", "g9"}:
        from runtime_notices import copy_runtime_notices

        notice_update = copy_runtime_notices(root, public)
        software_notices["files"].extend(notice_update.pop("files"))
        software_notices.update(notice_update)
        write_json(public / "licences/manifest.json", software_notices)
    for name in ("analysis_config.schema.json", "model_result.schema.json"):
        shutil.copyfile(root / "schemas" / name, data / name)
    excluded_sources = {
        rule["id"]: Policy.public_decision(rule)
        for rule in policy_data["rules"]
        if rule["status"] != "allowed"
    }
    for cell in [*cells.values(), *profile_cells.values(), *variant_cells.values()]:
        excluded_sources.update(cell["excluded_sources"])
    publication = {
        "mode": "static_candidate",
        "source_mode": mode,
        "approved": False,
        "notes_withheld": True,
        "policy_sha256": digest(policy_path.read_bytes()),
        "excluded_sources": list(excluded_sources.values()),
        "excluded_observations": sum(
            item["excluded_observations"]
            for group in (cells, profile_cells, variant_cells)
            for item in group.values()
        ),
        "licence_filter_applied": mode == "cleared",
        "local_only_comparison": mode == "all",
    }
    if candidate == "p2":
        publication.update(
            candidate="P2",
            parent_snapshot_id=snapshot["snapshot_id"],
            included_global_factors=["oil_brent", "us_policy_rate"],
            excluded_concepts=[
                {
                    "concept_id": "commod_idx",
                    "title": "Broad commodity index",
                    "reason": "Not included: Pink Sheet redistribution status remains unresolved.",
                }
            ],
            source_overrides=[
                {
                    "concept_id": "oil_brent",
                    "source": "EIA",
                    "source_series_id": "PET.RBRTE.M",
                    "source_snapshot_id": eia_marker["snapshot_id"],
                    "input_sha256": eia_marker["sha256"],
                    "source_release_date": eia_marker["source_release_date"],
                    "retrieved_utc": eia_marker["retrieved_utc"],
                    "audit_passed": True,
                }
            ],
        )
    validation = json.loads((root / "runs/g4/model-validation.json").read_text())
    if validation.get("status") != "passed":
        raise ValueError("A passed local model-validation report is required")
    import platform

    manifest = {
        "schema_version": 1,
        "snapshot_id": candidate_snapshot,
        "parent_snapshot_id": snapshot["snapshot_id"],
        "as_of_date": snapshot["as_of_date"],
        "publication_approved": False,
        "publication": publication,
        "countries": sorted(countries, key=lambda item: item["name"]),
        "indicators": indicators,
        "national_concepts": snapshot["national_concepts"],
        "global_factors": 2 if candidate == "p2" else snapshot["global_factors"],
        "global_factors_total": snapshot["global_factors"],
        "country_files": country_files,
        "templates": templates,
        "models": catalogue(),
        "sources": [
            {
                "name": rule.get("label", rule["id"]),
                "terms_url": rule.get("terms_url", ""),
                "terms_status": rule["status"],
                "attribution": rule.get("attribution", ""),
                "restrictions": rule.get("restrictions", ""),
            }
            for rule in policy_data["rules"]
        ],
        "coverage_summary": dict(Counter(row["status"] for row in coverage)),
        "coverage": coverage,
        "validation": {
            "gate": "G4",
            "models": validation["models"],
            "code_version": validation["code_version"],
        },
        "schema_url": "data/analysis_config.schema.json",
        "global_variants_url": "data/global-variants.json",
        "software_notices_url": "licences/manifest.json",
        "runtime": {
            "worker_url": "runtime/worker.mjs",
            "index_url": "runtime/pyodide/",
            "wheel_url": f"runtime/{wheel['wheel_file']}",
            "wheel_sha256": wheel["wheel_sha256"],
            "code_version": wheel["code_version"],
            "asset_lock_url": "runtime/assets.lock.json",
            "source_archive_sha256": wheel["source_archive_sha256"],
            "capabilities": ["run", "compatibility", "encode", "decode", "export"],
            "reproduction_environment": {
                "python_version": platform.python_version(),
                "dependencies": {name: version(name) for name in DEPENDENCIES},
            },
        },
    }
    write_json(data / "manifest.json", manifest)
    write_json(data / "publication-policy.json", policy_data)
    (public / ".nojekyll").write_text("")
    merged = {}
    for group in (accounting, profile_accounting, variant_accounting):
        for key, item in group.items():
            target_item = merged.setdefault(
                key,
                {
                    "source": item["source"],
                    "dataset_rules": item["dataset_rules"],
                    "input_observations": 0,
                    "retained_observations": 0,
                    "excluded_observations": 0,
                    "value_payload_bytes": 0,
                },
            )
            for field in (
                "input_observations",
                "retained_observations",
                "excluded_observations",
                "value_payload_bytes",
            ):
                target_item[field] += item[field]
    report = {
        "schema_version": 1,
        "snapshot_id": candidate_snapshot,
        "parent_snapshot_id": snapshot["snapshot_id"],
        "snapshot_manifest_sha256": digest(snapshot_bytes),
        "base_path": base_path,
        "source_mode": mode,
        "candidate": candidate,
        "public_directory": str(public.relative_to(root)),
        "build_directory": str((target / "site").relative_to(root)),
        "publication": publication,
        "coverage_summary": manifest["coverage_summary"],
        "templates": [{"id": t["id"], **t["publication"]} for t in templates],
        "source_accounting": merged,
        "software_notices": software_notices,
        "accounting_note": (
            "Source bytes count serialized observation/profile payload fragments, including "
            "repeated country/global factors and latest-profile copies. Remaining file bytes "
            "are shared metadata, JSON framing, code, fonts and pinned runtime. Derived "
            "observations occupy exclusive component-rule buckets, so component sources "
            "are not double counted."
        ),
        "network_requests": 0,
    }
    report["prepared_sizes"] = size_report(public, merged)
    write_json(target / "preparation.json", report)
    if (directory / "processed_manifest.json").read_bytes() != snapshot_bytes:
        raise ValueError("Accepted snapshot manifest changed during candidate preparation")
    return report


def size_report(directory: Path, accounting: dict[str, dict[str, Any]]) -> dict[str, Any]:
    files = {
        str(path.relative_to(directory)): path.stat().st_size
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }
    total = sum(files.values())
    values = sum(item["value_payload_bytes"] for item in accounting.values())
    return {
        "total_bytes": total,
        "file_count": len(files),
        "value_payload_bytes": values,
        "other_bytes": total - values,
        "largest_files": sorted(
            ({"path": path, "bytes": size} for path, size in files.items()),
            key=lambda item: item["bytes"],
            reverse=True,
        )[:15],
        "by_top_directory": {
            name: sum(size for path, size in files.items() if path.split("/")[0] == name)
            for name in sorted({path.split("/")[0] for path in files})
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", choices=("cleared", "all"), default="cleared")
    parser.add_argument("--base-path", default="/macrolab/")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--candidate", choices=("p1", "p2"), default="p1")
    args = parser.parse_args()
    result = prepare(mode=args.sources, base_path=args.base_path, candidate=args.candidate)
    if args.build:
        output = ROOT / result["build_directory"]
        if output.is_symlink() or not output.resolve().is_relative_to(
            (ROOT / "runs" / args.candidate).resolve()
        ):
            raise ValueError("Static output must remain in the dedicated ignored P1 directory")
        if output.exists():
            shutil.rmtree(output)
        environment = {
            **os.environ,
            "MACROLAB_BASE_PATH": args.base_path,
            "MACROLAB_PUBLIC_DIR": str(ROOT / result["public_directory"]),
            "MACROLAB_BUILD_DIR": str(output),
        }
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "web", env=environment, check=True)
        result["build_sizes"] = size_report(output, result["source_accounting"])
        write_json(output.parent / "build-report.json", result)
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "snapshot_id",
                    "source_mode",
                    "public_directory",
                    "build_directory",
                    "coverage_summary",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
