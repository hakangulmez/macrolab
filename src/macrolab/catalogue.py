"""Validate concept definitions and metadata-only, snapshot-backed source mappings."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from macrolab.data.coverage import LIMITING_REASON_CODES

FLOW_CONCEPTS = {"gdp_real", "cons_priv", "cons_gov", "gfcf", "exports_real", "imports_real"}
STOCK_CONCEPTS = {"credit_pnfs", "money_broad", "gov_debt"}
LEGACY_MAPPING_FIELDS = {
    "status",
    "first_date",
    "last_date",
    "observations",
    "frequency",
    "sources",
    "source_segments",
    "flags",
    "missing_periods",
    "requested_sample_start",
    "actual_available_start",
    "stale",
}
MAPPING_FIELDS = LEGACY_MAPPING_FIELDS | {"reason_code", "reason_codes"}
SOURCE_FIELDS = {
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
    "aggregation",
    "definition",
    "unit_label",
    "source_adjustment",
    "source_country",
    "euro_adoption",
    "first_date",
    "last_date",
}


class CatalogueError(ValueError):
    """A catalogue definition is missing or inconsistent."""


@dataclass(frozen=True)
class Concept:
    concept_id: str
    title: str
    scope: str
    native_frequency: str
    default_transform: str
    source_priority: tuple[str, ...]
    mapping_status: str


def project_root() -> Path:
    """Locate the source checkout."""
    return Path(__file__).resolve().parents[2]


def aggregation_rules(concept_id: str) -> dict[str, Any]:
    """Declare safe aggregation policy; G1 does not aggregate any observations."""
    stock = concept_id in STOCK_CONCEPTS
    return {
        "preserve_native_frequency": True,
        "monthly_to_quarterly": {
            "default": "mean",
            "optional": ["last"] if stock else [],
            "required_observations": 3,
            "last_condition": "verified point-in-time stock" if stock else None,
        },
        "quarterly_to_annual": {
            "default": "mean",
            "mean_applies_to": ["indices", "rates", "ratios"],
            "optional": ["last"] if stock else [],
            "last_condition": "verified point-in-time stock" if stock else None,
            "required_observations": 4,
            "conditional_sum_allowed": concept_id in FLOW_CONCEPTS,
            "sum_conditions": [
                "source metadata verifies an actual quarterly period flow in currency units",
                "not an index, rate, ratio, growth rate, or annualised/SAAR value",
                "all four quarters exist with consistent unit, multiplier and price basis",
                "reference/base year and seasonal adjustment are consistent",
            ]
            if concept_id in FLOW_CONCEPTS
            else [],
            "sum_without_verified_conditions": "forbidden",
        },
        "incomplete_periods": "reject; no interpolation or partial-period average",
        "metadata_changes": "reject aggregation across incompatible definitions or units",
    }


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogueError(f"{context} must be a non-empty string.")
    return value


def _strings(value: Any, context: str, *, empty_allowed: bool = True) -> list[str]:
    if (
        not isinstance(value, list)
        or (not value and not empty_allowed)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise CatalogueError(f"{context} must be a list of unique non-empty strings.")
    return value


def _integer(value: Any, context: str, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        bound = f" >= {minimum}" if minimum is not None else ""
        raise CatalogueError(f"{context} must be an integer{bound}.")
    return value


def _period(value: Any, frequency: str, context: str) -> int:
    text = _text(value, context)
    patterns = {"M": r"(\d{4})-(0[1-9]|1[0-2])", "Q": r"(\d{4})-Q([1-4])", "A": r"(\d{4})"}
    if frequency not in patterns or not (match := re.fullmatch(patterns[frequency], text)):
        raise CatalogueError(f"{context}: invalid {frequency} period {text!r}.")
    factor = {"M": 12, "Q": 4, "A": 1}[frequency]
    return int(match[1]) * factor + (int(match[2]) - 1 if frequency != "A" else 0)


def _iso_date(value: Any, context: str) -> None:
    try:
        date.fromisoformat(_text(value, context))
    except ValueError as exc:
        raise CatalogueError(f"{context} must be an ISO calendar date.") from exc


def _audit_summary(audit: Any, context: str) -> dict[str, Any]:
    if not isinstance(audit, dict) or audit.get("passed") is not True:
        raise CatalogueError(f"{context} requires passed independent raw-value audits.")
    for key in ("required_checks", "performed_checks", "matched", "mismatches", "unavailable"):
        _integer(audit.get(key), f"{context}.{key}", minimum=0)
    if not (
        audit["required_checks"] > 0
        and audit["required_checks"] == audit["performed_checks"] == audit["matched"]
        and audit["mismatches"] == audit["unavailable"] == 0
    ):
        raise CatalogueError(f"{context} overstates verification.")
    return audit


def _unchanged_provenance(provenance: dict[str, Any], unchanged_concepts: set[str]) -> None:
    """A scoped refresh must retain a verified base and exact unchanged-row evidence."""
    base, proof = provenance.get("base_snapshot"), provenance.get("unchanged_proof")
    if not unchanged_concepts and base is None and proof is None:
        return
    if not isinstance(base, dict) or not isinstance(proof, dict):
        raise CatalogueError("Scoped G1_1 audits require base_snapshot and unchanged_proof.")
    _text(base.get("snapshot_id"), "base_snapshot.snapshot_id")
    path = Path(_text(base.get("destination"), "base_snapshot.destination"))
    if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("data", "processed"):
        raise CatalogueError("Base snapshot destination must stay in data/processed.")
    for field, value in (
        ("base_snapshot.manifest_sha256", base.get("manifest_sha256")),
        ("unchanged_proof.before_hash", proof.get("before_hash")),
        ("unchanged_proof.after_hash", proof.get("after_hash")),
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", str(value)):
            raise CatalogueError(f"{field} must be a SHA-256 digest.")
    _audit_summary(base.get("audit_summary"), "base_snapshot.audit_summary")
    unaffected = _strings(proof.get("concept_ids"), "unchanged_proof.concept_ids")
    if set(unaffected) != unchanged_concepts:
        raise CatalogueError("Unchanged proof must cover exactly the unaudited concepts.")
    _integer(proof.get("rows"), "unchanged_proof.rows", minimum=0)
    if proof["before_hash"] != proof["after_hash"] or any(
        proof.get(key) is not True
        for key in ("passed", "profiles_unchanged", "variants_unchanged", "countries_unchanged")
    ):
        raise CatalogueError("Unaudited concepts or supporting metadata changed.")


def _provenance(document: dict[str, Any]) -> set[str]:
    provenance = document.get("snapshot_provenance")
    if not isinstance(provenance, dict):
        raise CatalogueError("G1 mappings require snapshot_provenance.")
    for field in ("snapshot_id", "code_version", "built_utc"):
        _text(provenance.get(field), f"snapshot_provenance.{field}")
    for field in ("processed_manifest_sha256", "series_cards_sha256", "observations_hash"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(provenance.get(field, ""))):
            raise CatalogueError(f"snapshot_provenance.{field} must be a SHA-256 digest.")
    for field in ("processed_manifest_path", "series_cards_path"):
        path = Path(_text(provenance.get(field), f"snapshot_provenance.{field}"))
        if path.is_absolute() or ".." in path.parts or path.parts[:2] != ("data", "processed"):
            raise CatalogueError(f"snapshot_provenance.{field} must stay in data/processed.")
    _iso_date(provenance.get("as_of_date"), "snapshot_provenance.as_of_date")
    if provenance.get("verification") != "completed_snapshot_and_cards_hash_verified":
        raise CatalogueError("G1 provenance must identify completed snapshot/hash verification.")
    if provenance.get("validation_passed") is not True:
        raise CatalogueError("G1 provenance requires passed snapshot validation.")
    audit = _audit_summary(provenance.get("audit_summary"), "audit_summary")
    if document.get("stage") == "G1_1":
        scope = _strings(provenance.get("audit_scope"), "audit_scope", empty_allowed=False)
        concept_ids = {item["concept_id"] for item in document["concepts"]}
        if not set(scope) <= concept_ids or audit["required_checks"] != 9 * len(scope):
            raise CatalogueError("G1_1 requires nine independent checks per audited concept.")
        _unchanged_provenance(provenance, concept_ids - set(scope))
    inputs = provenance.get("processing_inputs")
    if (
        not isinstance(inputs, dict)
        or not isinstance(inputs.get("files"), dict)
        or not inputs["files"]
    ):
        raise CatalogueError("G1 processing input fingerprints are required.")
    for name, digest in inputs["files"].items():
        path = Path(_text(name, "processing input path"))
        if path.is_absolute() or ".." in path.parts:
            raise CatalogueError("Processing input paths must be project-relative.")
        if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
            raise CatalogueError("Processing input files require SHA-256 digests.")
    if not re.fullmatch(r"[0-9a-f]{64}", str(inputs.get("concept_definitions_sha256", ""))):
        raise CatalogueError("Concept definitions require a SHA-256 digest.")
    payload = {key: inputs[key] for key in ("files", "concept_definitions_sha256")}
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if inputs.get("fingerprint") != fingerprint:
        raise CatalogueError("Processing input fingerprint is inconsistent.")
    if provenance.get("offline_rebuild"):
        replay = provenance.get("replay_comparison")
        if not isinstance(replay, dict) or any(
            type(replay.get(key)) is not bool
            for key in ("same_processing_inputs", "observations_match", "coverage_match")
        ):
            raise CatalogueError("Offline provenance requires a replay comparison.")
        if replay["same_processing_inputs"] and not (
            replay["observations_match"] and replay["coverage_match"]
        ):
            raise CatalogueError("Unchanged processing inputs failed exact replay.")
    countries = _strings(provenance.get("country_codes"), "country_codes", empty_allowed=False)
    if any(not re.fullmatch(r"[A-Z]{3}|EA", code) for code in countries):
        raise CatalogueError("country_codes must contain ISO3 codes or EA.")
    if provenance.get("country_count") != len(countries):
        raise CatalogueError("snapshot_provenance country count does not match country_codes.")
    return set(countries)


def mapping_status(mappings: dict[str, Any], *, stage: str = "G1_1") -> str:
    """Summarise coverage, keeping historical G1 labels readable."""
    statuses = {entry["status"] for entry in mappings.values()}
    if statuses == {"available"}:
        return "verified"
    if statuses == {"missing"}:
        return "unavailable"
    if stage == "G1":
        return "partial"
    return "verified_with_notes" if statuses <= {"available", "available_note"} else "limited"


def _mapping(entry: Any, context: str, *, stage: str) -> None:
    current = stage == "G1_1"
    fields = MAPPING_FIELDS if current else LEGACY_MAPPING_FIELDS
    if not isinstance(entry, dict) or set(entry) != fields:
        raise CatalogueError(f"{context}: requires exactly the metadata-only mapping fields.")
    status = entry["status"]
    statuses = (
        {"available", "available_note", "limited", "missing"}
        if current
        else {"available", "partial", "missing"}
    )
    if status not in statuses:
        raise CatalogueError(f"{context}: unknown coverage status.")
    if current:
        reasons = _strings(entry["reason_codes"], f"{context}.reason_codes", empty_allowed=False)
        if entry["reason_code"] != reasons[0]:
            raise CatalogueError(f"{context}: primary reason must be the first reason code.")
        has_limit = bool(set(reasons) & set(LIMITING_REASON_CODES))
        if (
            (status == "available" and reasons != ["coverage_complete"])
            or (status in {"available", "available_note"} and has_limit)
            or (status == "limited" and not has_limit)
            or (status != "available" and "coverage_complete" in reasons)
        ):
            raise CatalogueError(f"{context}: coverage status contradicts its reason codes.")
    flags = _strings(entry["flags"], f"{context}.flags")
    sources = _strings(entry["sources"], f"{context}.sources")
    observations = _integer(entry["observations"], f"{context}.observations", minimum=0)
    _iso_date(entry["requested_sample_start"], f"{context}.requested_sample_start")
    if type(entry["stale"]) is not bool:
        raise CatalogueError(f"{context}.stale must be a boolean.")
    segments = entry["source_segments"]
    if not isinstance(segments, list):
        raise CatalogueError(f"{context}.source_segments must be a list.")
    if status == "missing":
        if (
            observations
            or sources
            or segments
            or not flags
            or any(
                entry[key] is not None
                for key in (
                    "frequency",
                    "first_date",
                    "last_date",
                    "actual_available_start",
                    "missing_periods",
                )
            )
        ):
            raise CatalogueError(
                f"{context}: missing coverage needs a reason and no claimed observations."
            )
        return
    if not observations or not sources or not segments:
        raise CatalogueError(f"{context}: populated mappings require observations and sources.")
    if status == "partial" and not flags:
        raise CatalogueError(f"{context}: partial coverage requires warning flags.")
    freq = entry["frequency"]
    first = _period(entry["first_date"], freq, context)
    last = _period(entry["last_date"], freq, context)
    gaps = _integer(entry["missing_periods"], f"{context}.missing_periods", minimum=0)
    if status in {"available", "available_note"} and (gaps or entry["stale"]):
        raise CatalogueError(f"{context}: stale or gapped coverage cannot be available.")
    if first > last or last - first + 1 != observations + gaps:
        raise CatalogueError(f"{context}: dates, observation count and gaps are inconsistent.")
    if entry["actual_available_start"] is None:
        if "no_observations_in_requested_sample" not in flags:
            raise CatalogueError(
                f"{context}: actual sample start requires evidence or an explicit warning."
            )
    else:
        _iso_date(entry["actual_available_start"], f"{context}.actual_available_start")
    identities: set[tuple[str, str]] = set()
    segment_starts, segment_ends = [], []
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != SOURCE_FIELDS:
            raise CatalogueError(f"{context}: incomplete or non-metadata source segment.")
        for field in (
            "source",
            "source_series_id",
            "source_url",
            "attribution",
            "terms_status",
            "unit",
            "price_basis",
        ):
            _text(segment[field], f"{context}.{field}")
        for field in (
            "definition",
            "unit_label",
            "source_adjustment",
            "source_country",
            "euro_adoption",
            "source_geo",
            "variant",
            "source_unit",
            "aggregation",
        ):
            if segment[field] is not None:
                _text(segment[field], f"{context}.{field}")
        if segment["shared"] is not None and type(segment["shared"]) is not bool:
            raise CatalogueError(f"{context}.shared must be a boolean or null.")
        if segment["euro_adoption"] is not None:
            _iso_date(segment["euro_adoption"], f"{context}.euro_adoption")
        parsed = urlsplit(segment["source_url"])
        if parsed.scheme != "https" or not parsed.netloc:
            raise CatalogueError(f"{context}: source_url must be an HTTPS source reference.")
        _integer(segment["unit_mult"], f"{context}.unit_mult")
        if segment["sa_flag"] not in {"SA", "NSA", "NA", "UNKNOWN"}:
            raise CatalogueError(f"{context}: invalid seasonal adjustment.")
        if segment["base_year"] is not None:
            _text(segment["base_year"], f"{context}.base_year")
        if segment["freq"] != freq:
            raise CatalogueError(f"{context}: source frequency differs from the mapped frequency.")
        start = _period(segment["first_date"], freq, context)
        end = _period(segment["last_date"], freq, context)
        if not first <= start <= end <= last:
            raise CatalogueError(f"{context}: source segment dates lie outside mapped coverage.")
        identity = (segment["source"], segment["source_series_id"])
        if identity in identities:
            raise CatalogueError(f"{context}: duplicate source-series segment.")
        identities.add(identity)
        segment_starts.append(start)
        segment_ends.append(end)
    if sources != sorted({source for source, _ in identities}):
        raise CatalogueError(f"{context}: source list differs from selected source segments.")
    if min(segment_starts) != first or max(segment_ends) != last:
        raise CatalogueError(f"{context}: source segments do not support the claimed date range.")


def validate_catalogue(document: Any) -> tuple[Concept, ...]:
    """Validate G0 fixtures, historical G1, or reason-coded G1_1 snapshot mappings."""
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise CatalogueError("Catalogue must be a mapping with schema_version: 1.")
    definitions = document.get("concepts")
    if not isinstance(definitions, list) or not definitions:
        raise CatalogueError("Catalogue concepts must be a non-empty list.")
    stage = _text(document.get("stage", "G0"), "stage")
    if stage not in {"G0", "G1", "G1_1"}:
        raise CatalogueError("Catalogue stage must be G0, G1 or G1_1.")
    is_g1 = stage in {"G1", "G1_1"}
    countries = _provenance(document) if is_g1 else set()
    concepts: list[Concept] = []
    seen: set[str] = set()
    required_strings = (
        "concept_id",
        "title",
        "scope",
        "native_frequency",
        "default_transform",
        "mapping_status",
    )
    allowed_transforms = {"level", "log", "diff", "log_diff", "yoy_pct", "yoy_diff", "qoq_saar"}
    for index, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            raise CatalogueError(f"Concept at index {index} must be a mapping.")
        for field in required_strings:
            _text(definition.get(field), f"Concept at index {index}.{field}")
        concept_id = definition["concept_id"]
        if concept_id in seen:
            raise CatalogueError(f"Duplicate concept_id: {concept_id}.")
        seen.add(concept_id)
        if definition["scope"] not in {"national", "global"}:
            raise CatalogueError(f"{concept_id}: scope must be national or global.")
        if definition["native_frequency"] not in {"M", "Q", "A"}:
            raise CatalogueError(f"{concept_id}: native_frequency must be M, Q or A.")
        if definition["default_transform"] not in allowed_transforms:
            raise CatalogueError(f"{concept_id}: unknown default_transform.")
        priorities = _strings(
            definition.get("source_priority"), f"{concept_id}.source_priority", empty_allowed=False
        )
        mappings = definition.get("country_mappings")
        if not is_g1:
            if definition["mapping_status"] != "unresolved" or mappings != {}:
                raise CatalogueError(
                    f"{concept_id}: G0 definitions must leave country mappings unresolved."
                )
        else:
            if not isinstance(mappings, dict) or set(mappings) != countries:
                raise CatalogueError(
                    f"{concept_id}: G1 requires coverage for every snapshot country."
                )
            for country, entry in mappings.items():
                _mapping(entry, f"{concept_id}/{country}", stage=stage)
            if definition["mapping_status"] != mapping_status(mappings, stage=stage):
                raise CatalogueError(
                    f"{concept_id}: mapping_status overstates or contradicts coverage."
                )
            if definition.get("aggregation_rules") != aggregation_rules(concept_id):
                raise CatalogueError(
                    f"{concept_id}: safe, explicit aggregation_rules are required."
                )
        concepts.append(
            Concept(
                concept_id=concept_id,
                title=definition["title"],
                scope=definition["scope"],
                native_frequency=definition["native_frequency"],
                default_transform=definition["default_transform"],
                source_priority=tuple(priorities),
                mapping_status=definition["mapping_status"],
            )
        )
    return tuple(concepts)


def load_catalogue(path: Path | None = None) -> tuple[Concept, ...]:
    catalogue_path = path or project_root() / "configs" / "indicators.yaml"
    with catalogue_path.open(encoding="utf-8") as handle:
        return validate_catalogue(yaml.safe_load(handle))


def catalogue_summary(path: Path | None = None) -> dict[str, Any]:
    concepts = load_catalogue(path)
    national_count = sum(concept.scope == "national" for concept in concepts)
    counts = dict(sorted(Counter(concept.mapping_status for concept in concepts).items()))
    unresolved = set(counts) == {"unresolved"}
    return {
        "national_concepts": national_count,
        "global_factors": sum(concept.scope == "global" for concept in concepts),
        "series_families": len(concepts),
        "ui_label": f"{national_count} indicators",
        "mapping_status": (
            "unresolved; source and country mappings are scheduled for G1"
            if unresolved
            else "snapshot-backed mappings; inspect country coverage and warning flags"
        ),
        "concept_mapping_counts": counts,
    }
