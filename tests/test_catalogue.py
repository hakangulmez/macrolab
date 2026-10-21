from __future__ import annotations

import hashlib
import json
import runpy
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from macrolab.catalogue import (
    CatalogueError,
    aggregation_rules,
    catalogue_summary,
    load_catalogue,
    mapping_status,
    validate_catalogue,
)

UPDATER = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/update_g1_catalogue.py")
)


def definition() -> dict[str, Any]:
    return {
        "concept_id": "gdp_real",
        "title": "Real GDP",
        "scope": "national",
        "native_frequency": "Q",
        "default_transform": "yoy_pct",
        "source_priority": ["OECD QNA"],
        "mapping_status": "unresolved",
        "country_mappings": {},
    }


def test_catalogue_matches_approved_concept_scope() -> None:
    concepts = load_catalogue()
    national = {concept.concept_id for concept in concepts if concept.scope == "national"}
    assert national == {
        "gdp_real",
        "cons_priv",
        "gfcf",
        "cons_gov",
        "exports_real",
        "imports_real",
        "ind_prod",
        "retail_vol",
        "cli",
        "cpi",
        "cpi_core",
        "ppi",
        "gdp_defl",
        "house_real",
        "ulc",
        "unemp",
        "employment",
        "lfpr",
        "policy_rate",
        "rate_3m",
        "rate_10y",
        "term_spread",
        "credit_pnfs",
        "money_broad",
        "equity_idx",
        "reer",
        "neer",
        "fx_usd",
        "ca_gdp",
        "gov_debt",
        "gov_balance",
        "conf_cons",
        "conf_bus",
    }
    assert {concept.concept_id for concept in concepts if concept.scope == "global"} == {
        "oil_brent",
        "commod_idx",
        "us_policy_rate",
    }
    assert catalogue_summary()["ui_label"] == "33 indicators"
    assert catalogue_summary()["series_families"] == 36


def test_g0_unresolved_fixture_remains_valid() -> None:
    document = {"schema_version": 1, "concepts": [definition()]}
    assert validate_catalogue(document)[0].mapping_status == "unresolved"


def test_catalogue_rejects_duplicate_concepts(tmp_path: Path) -> None:
    item = definition()
    path = tmp_path / "duplicate.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "concepts": [item, item]}))
    with pytest.raises(CatalogueError, match="Duplicate concept_id: gdp_real"):
        load_catalogue(path)


def test_catalogue_rejects_premature_mapping_claim() -> None:
    item = {**definition(), "mapping_status": "verified"}
    with pytest.raises(CatalogueError, match="leave country mappings unresolved"):
        validate_catalogue({"schema_version": 1, "concepts": [item]})


def card(country: str, status: str) -> dict[str, Any]:
    missing = status == "missing"
    reason = (
        "no_verified_mapping_or_observations"
        if missing
        else ("stale" if status == "limited" else "coverage_complete")
    )
    return {
        "country": country,
        "concept_id": "gdp_real",
        "status": status,
        "first_date": None if missing else "1999-Q1",
        "last_date": None if missing else "1999-Q2",
        "observations": 0 if missing else 2,
        "frequency": None if missing else "Q",
        "sources": [] if missing else ["OECD"],
        "source_segments": []
        if missing
        else [
            {
                "source": "OECD",
                "source_series_id": f"QNA/Q.Y.{country}.IX.LR",
                "source_url": "https://sdmx.oecd.org/public/rest/v1/data/test",
                "attribution": "OECD synthetic metadata fixture",
                "terms_status": "local_only_publication_requires_owner_approval",
                "unit": "IX",
                "unit_mult": 0,
                "sa_flag": "SA",
                "price_basis": "chain_linked_volume",
                "base_year": "2015",
                "freq": "Q",
                "shared": False,
                "source_geo": country,
                "variant": None,
                "source_unit": None,
                "aggregation": None,
                "definition": "Quarterly volume index",
                "unit_label": "Index",
                "source_adjustment": "Y",
                "source_country": country,
                "euro_adoption": "1999-01-01" if country == "DEU" else None,
                "first_date": "1999-Q1",
                "last_date": "1999-Q2",
            }
        ],
        "flags": ["no_verified_mapping_or_observations"]
        if missing
        else (["stale"] if status == "limited" else []),
        "missing_periods": None if missing else 0,
        "requested_sample_start": "1999-01-01",
        "actual_available_start": None if missing else "1999-01-01",
        "stale": status == "limited",
        "reason_code": reason,
        "reason_codes": [reason],
    }


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    root = tmp_path
    destination = root / "data/processed/snapshots/20261020-0000"
    destination.mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "configs/indicators.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "concepts": [definition()],
            }
        )
    )
    cards = [card("DEU", "available"), card("CAN", "limited"), card("JPN", "missing")]
    cards[0]["values"] = [123456.789]  # Never copy arbitrary card or segment payloads.
    cards[0]["source_segments"][0]["value"] = 123456.789
    payload = json.dumps(cards).encode()
    (destination / "series_cards.json").write_bytes(payload)
    manifest = {
        "schema_version": 1,
        "snapshot_id": "20261020-0000",
        "as_of_date": "2026-10-20",
        "built_utc": "2026-10-20T10:00:00+00:00",
        "offline_rebuild": False,
        "destination": str(destination.relative_to(root)),
        "code_version": "a" * 40,
        "code_dirty": False,
        "validation_passed": True,
        "processing_inputs": {
            "files": {"configs/data_rules.yaml": "c" * 64},
            "concept_definitions_sha256": "d" * 64,
        },
        "observations_hash": "b" * 64,
        "observations": 4,
        "countries": 3,
        "national_concepts": 1,
        "global_factors": 0,
        "raw_verification": {"request_records": 2, "response_hashes_verified": 2},
        "audit_summary": {
            "required_checks": 9,
            "performed_checks": 9,
            "matched": 9,
            "mismatches": 0,
            "unavailable": 0,
            "passed": True,
        },
        "audit_scope": ["gdp_real"],
        "files": {
            "series_cards.json": {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        },
    }
    manifest["processing_inputs"]["fingerprint"] = hashlib.sha256(
        json.dumps(
            manifest["processing_inputs"],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    (destination / "processed_manifest.json").write_text(json.dumps(manifest))
    (root / "data/processed/current").symlink_to(
        "snapshots/20261020-0000", target_is_directory=True
    )
    markers = root / "data/manifests/snapshots"
    markers.mkdir(parents=True)
    (markers / "20261020-0000.json").write_text(
        json.dumps(
            {
                "snapshot_id": "20261020-0000",
                "as_of_date": "2026-10-20",
                "status": "complete",
                "processed_manifest": str(
                    (destination / "processed_manifest.json").relative_to(root)
                ),
            }
        )
    )
    return root


def test_g1_updater_writes_only_verified_metadata_and_keeps_limits(snapshot: Path) -> None:
    result = UPDATER["update_catalogue"](snapshot)
    document = yaml.safe_load((snapshot / "configs/indicators.yaml").read_text())
    item = document["concepts"][0]
    assert result["written"] and not result["observation_values_written"]
    assert load_catalogue(snapshot / "configs/indicators.yaml")[0].mapping_status == "limited"
    assert document["stage"] == "G1_1"
    assert item["country_mappings"]["CAN"]["reason_code"] == "stale"
    assert item["country_mappings"]["JPN"]["status"] == "missing"
    assert item["country_mappings"]["CAN"]["flags"] == ["stale"]
    source = item["country_mappings"]["DEU"]["source_segments"][0]
    assert source["source_series_id"] == "QNA/Q.Y.DEU.IX.LR"
    assert source["unit_mult"] == 0 and source["base_year"] == "2015"
    assert source["source_adjustment"] == "Y" and source["euro_adoption"] == "1999-01-01"
    assert document["snapshot_provenance"]["audit_summary"]["passed"] is True
    assert "123456.789" not in json.dumps(document)
    assert "values" not in item["country_mappings"]["DEU"]
    assert "value" not in source


def test_g1_check_does_not_write(snapshot: Path) -> None:
    path = snapshot / "configs/indicators.yaml"
    before = path.read_bytes()
    assert UPDATER["update_catalogue"](snapshot, check=True)["written"] is False
    assert path.read_bytes() == before


def test_historical_g1_partial_mappings_still_load(snapshot: Path) -> None:
    document = UPDATER["proposed_catalogue"](snapshot)
    document["stage"] = "G1"
    concept = document["concepts"][0]
    concept["mapping_status"] = "partial"
    for entry in concept["country_mappings"].values():
        entry.pop("reason_code")
        entry.pop("reason_codes")
        if entry["status"] == "limited":
            entry["status"] = "partial"
    assert validate_catalogue(document)[0].mapping_status == "partial"


def test_g11_notes_do_not_imply_limited_concept_coverage() -> None:
    mappings = {"DEU": {"status": "available"}, "CAN": {"status": "available_note"}}
    assert mapping_status(mappings) == "verified_with_notes"


@pytest.mark.parametrize(
    "failure",
    ["legacy_status", "missing_reason", "contradictory_reason", "audit_count", "audit_scope"],
)
def test_g11_requires_new_status_reasons_and_scoped_audit_evidence(
    snapshot: Path,
    failure: str,
) -> None:
    document = UPDATER["proposed_catalogue"](snapshot)
    entry = document["concepts"][0]["country_mappings"]["CAN"]
    if failure == "legacy_status":
        entry["status"] = "partial"
    elif failure == "missing_reason":
        entry.pop("reason_code")
    elif failure == "contradictory_reason":
        entry["status"] = "available_note"
    elif failure == "audit_count":
        for key in ("required_checks", "performed_checks", "matched"):
            document["snapshot_provenance"]["audit_summary"][key] = 18
    else:
        document["snapshot_provenance"]["audit_scope"] = ["unrelated_concept"]
    with pytest.raises(CatalogueError):
        validate_catalogue(document)


def scoped_document(snapshot: Path) -> dict[str, Any]:
    document: dict[str, Any] = UPDATER["proposed_catalogue"](snapshot)
    unchanged = deepcopy(document["concepts"][0])
    unchanged["concept_id"] = "cons_priv"
    document["concepts"].append(unchanged)
    provenance = document["snapshot_provenance"]
    provenance["base_snapshot"] = {
        "snapshot_id": "20261019-0000",
        "destination": "data/processed/snapshots/20261019-0000",
        "manifest_sha256": "e" * 64,
        "audit_summary": deepcopy(provenance["audit_summary"]),
    }
    provenance["unchanged_proof"] = {
        "concept_ids": ["cons_priv"],
        "before_hash": "f" * 64,
        "after_hash": "f" * 64,
        "passed": True,
        "rows": 4,
        "profiles_unchanged": True,
        "variants_unchanged": True,
        "countries_unchanged": True,
    }
    return document


def test_scoped_audit_retains_unchanged_concepts_only_with_exact_proof(snapshot: Path) -> None:
    assert len(validate_catalogue(scoped_document(snapshot))) == 2


@pytest.mark.parametrize(
    "failure",
    [
        "omitted_proof",
        "wrong_complement",
        "changed_values",
        "changed_profiles",
        "failed_base_audit",
    ],
)
def test_scoped_audit_cannot_overstate_unchanged_concept_verification(
    snapshot: Path,
    failure: str,
) -> None:
    document = scoped_document(snapshot)
    provenance = document["snapshot_provenance"]
    proof = provenance["unchanged_proof"]
    if failure == "omitted_proof":
        provenance.pop("unchanged_proof")
    elif failure == "wrong_complement":
        proof["concept_ids"] = ["gdp_real"]
    elif failure == "changed_values":
        proof["after_hash"] = "0" * 64
    elif failure == "changed_profiles":
        proof["profiles_unchanged"] = False
    else:
        provenance["base_snapshot"]["audit_summary"]["passed"] = False
    with pytest.raises(CatalogueError):
        validate_catalogue(document)


def test_updater_independently_checks_base_manifest_hash(snapshot: Path) -> None:
    current_path = snapshot / "data/processed/current/processed_manifest.json"
    current = json.loads(current_path.read_text())
    base = deepcopy(current)
    base["snapshot_id"] = "20261019-0000"
    base["destination"] = "data/processed/snapshots/20261019-0000"
    base_path = snapshot / base["destination"] / "processed_manifest.json"
    base_path.parent.mkdir(parents=True)
    base_bytes = json.dumps(base).encode()
    base_path.write_bytes(base_bytes)
    current["base_snapshot"] = {
        "snapshot_id": base["snapshot_id"],
        "destination": base["destination"],
        "manifest_sha256": hashlib.sha256(base_bytes).hexdigest(),
        "audit_summary": base["audit_summary"],
    }
    current["unchanged_proof"] = {
        "concept_ids": [],
        "before_hash": "f" * 64,
        "after_hash": "f" * 64,
        "passed": True,
        "rows": 0,
        "profiles_unchanged": True,
        "variants_unchanged": True,
        "countries_unchanged": True,
    }
    current_path.write_text(json.dumps(current))
    document = UPDATER["proposed_catalogue"](snapshot)
    assert document["snapshot_provenance"]["base_snapshot"] == current["base_snapshot"]
    base_path.write_bytes(base_bytes + b" ")
    with pytest.raises(CatalogueError, match="Base snapshot hash"):
        UPDATER["proposed_catalogue"](snapshot)


@pytest.mark.parametrize(
    "failure", ["incomplete", "tampered_cards", "wrong_count", "failed_validation", "failed_audit"]
)
def test_g1_updater_rejects_unproven_snapshot_without_writing(snapshot: Path, failure: str) -> None:
    original = (snapshot / "configs/indicators.yaml").read_bytes()
    if failure == "incomplete":
        path = snapshot / "data/manifests/snapshots/20261020-0000.json"
        value = json.loads(path.read_text())
        value["status"] = "fetching"
        path.write_text(json.dumps(value))
    elif failure == "tampered_cards":
        path = snapshot / "data/processed/current/series_cards.json"
        path.write_bytes(path.read_bytes() + b" ")
    else:
        path = snapshot / "data/processed/current/processed_manifest.json"
        value = json.loads(path.read_text())
        if failure == "wrong_count":
            value["observations"] = 100
        elif failure == "failed_validation":
            value["validation_passed"] = False
        else:
            value["audit_summary"]["passed"] = False
        path.write_text(json.dumps(value))
    with pytest.raises(CatalogueError):
        UPDATER["update_catalogue"](snapshot)
    assert (snapshot / "configs/indicators.yaml").read_bytes() == original


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "no_provenance",
        "no_series_id",
        "wrong_units",
        "date_claim",
        "overstated",
        "raw_value",
        "unsafe_sum",
    ],
)
def test_g1_rejects_empty_unproven_or_unsafe_mapping_claims(snapshot: Path, failure: str) -> None:
    document = deepcopy(UPDATER["proposed_catalogue"](snapshot))
    concept = document["concepts"][0]
    entry = concept["country_mappings"]["DEU"]
    if failure == "empty":
        concept["country_mappings"] = {}
    elif failure == "no_provenance":
        document.pop("snapshot_provenance")
    elif failure == "no_series_id":
        entry["source_segments"][0]["source_series_id"] = ""
    elif failure == "wrong_units":
        entry["source_segments"][0]["unit_mult"] = True
    elif failure == "date_claim":
        entry["last_date"] = "2026-Q3"
    elif failure == "overstated":
        concept["mapping_status"] = "verified"
    elif failure == "raw_value":
        entry["value"] = 123.4
    else:
        concept["aggregation_rules"]["quarterly_to_annual"]["sum_conditions"] = []
    with pytest.raises(CatalogueError):
        validate_catalogue(document)


def test_aggregation_policy_distinguishes_flow_currency_indices_and_stocks() -> None:
    for concept in ("gdp_real", "cons_priv", "gfcf", "cons_gov", "exports_real", "imports_real"):
        rules = aggregation_rules(concept)
        annual = rules["quarterly_to_annual"]
        assert rules["monthly_to_quarterly"]["default"] == "mean"
        assert annual["default"] == "mean" and annual["conditional_sum_allowed"]
        assert any("not an index" in condition for condition in annual["sum_conditions"])
        assert annual["required_observations"] == 4
        assert annual["sum_without_verified_conditions"] == "forbidden"
    for concept in ("cpi", "rate_3m", "gdp_defl", "ca_gdp", "gov_balance", "oil_brent"):
        assert aggregation_rules(concept)["quarterly_to_annual"]["conditional_sum_allowed"] is False
    for concept in ("money_broad", "credit_pnfs", "gov_debt"):
        rules = aggregation_rules(concept)
        assert rules["monthly_to_quarterly"]["optional"] == ["last"]
        assert rules["quarterly_to_annual"]["optional"] == ["last"]
        assert rules["quarterly_to_annual"]["conditional_sum_allowed"] is False
        assert rules["preserve_native_frequency"] is True


@pytest.mark.parametrize("changed_inputs", [True, False])
def test_replay_contract_requires_exact_results_only_for_same_inputs(
    snapshot: Path,
    changed_inputs: bool,
) -> None:
    manifest_path = snapshot / "data/processed/current/processed_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["offline_rebuild"] = True
    manifest["replay_comparison"] = {
        "baseline_destination": "data/processed/snapshots/20261020-0000",
        "same_processing_inputs": not changed_inputs,
        "observations_match": False,
        "coverage_match": False,
    }
    manifest_path.write_text(json.dumps(manifest))
    if changed_inputs:
        proposed = UPDATER["proposed_catalogue"](snapshot)
        assert proposed["snapshot_provenance"]["replay_comparison"]["coverage_match"] is False
        assert validate_catalogue(proposed)[0].mapping_status == "limited"
    else:
        with pytest.raises(CatalogueError, match="Identical processing inputs"):
            UPDATER["proposed_catalogue"](snapshot)
