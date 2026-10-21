"""Publication candidates fail closed without touching accepted local observations."""

import json
import runpy
from copy import deepcopy
from pathlib import Path

import pytest

from macrolab.analysis.data import prepare_country

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/p1_prepare.py"))
Policy = MODULE["Policy"]
filter_rows = MODULE["filter_rows"]


def rules():
    return {
        "rules": [
            {
                "id": "bis",
                "source": "BIS",
                "dataset": "BIS",
                "status": "allowed",
                "terms_url": "https://data.bis.org/help/legal",
                "restrictions": ["Credit BIS"],
            },
            {"id": "oecd", "source": "OECD", "dataset": "OECD", "status": "unclear"},
            {"id": "imf", "source": "IMF", "dataset": "IMF", "status": "not_allowed"},
            {
                "id": "worldbank_wdi",
                "source": "WorldBank",
                "dataset": "WDI",
                "status": "allowed",
                "source_url_prefixes": ["https://api.worldbank.org/v2/"],
                "attribution_by_series": {
                    "SP.POP.TOTL": "UN Population Division and national providers"
                },
                "terms_url": "https://data.worldbank.org/summary-terms-of-use",
            },
            {
                "id": "worldbank_pink_sheet",
                "source": "WorldBank",
                "dataset": "Pink Sheet",
                "status": "unclear",
                "series_id_prefixes": ["PinkSheet/"],
            },
        ]
    }


def row(source="BIS", period="2000-Q1", **changes):
    return {
        "country": "USA",
        "concept_id": "policy_rate",
        "source": source,
        "source_series_id": "series",
        "source_url": "https://source.example/series",
        "date": period,
        "value": 2.5,
        "freq": "Q",
        "unit": "percent",
        "unit_mult": 0,
        "price_basis": "nominal",
        "sa_flag": "NA",
        "base_year": None,
        "obs_status": "reported",
        "flags": "[]",
        "audit": {"parser": "csv"},
        "raw_path": "data/raw/private-location.bin",
        **changes,
    }


def test_mixed_series_retains_only_cleared_observations_and_preserves_inputs():
    original = [row(), row("OECD", "2000-Q2"), row("IMF", "2000-Q3")]
    before = deepcopy(original)
    kept, cells, accounting = filter_rows(original, Policy(rules()), "cleared")
    assert [(item["date"], item["value"]) for item in kept] == [("2000-Q1", 2.5)]
    assert cells[("USA", "policy_rate")]["excluded_observations"] == 2
    assert set(cells[("USA", "policy_rate")]["excluded_sources"]) == {"oecd", "imf"}
    assert accounting["bis"]["retained_observations"] == 1
    assert "audit" not in kept[0] and "raw_path" not in kept[0]
    assert kept[0]["publication_restrictions"] == ["Credit BIS"]
    assert original == before


@pytest.mark.parametrize(
    "component,retained", [("BIS", True), ("OECD", False), ("IMF", False), ("Unknown", False)]
)
def test_derived_value_requires_every_nested_component_to_be_cleared(component, retained):
    nested = row("Derived", audit={"components": [row(), row(component)]})
    outer = row("Derived", audit=json.dumps({"components": [row(), nested]}))
    kept, _, accounting = filter_rows([outer], Policy(rules()), "cleared")
    assert bool(kept) is retained
    assert sum(item["input_observations"] for item in accounting.values()) == 1
    if kept:
        assert kept[0]["value"] == outer["value"]


def test_missing_or_ambiguous_provenance_never_uses_an_allow_rule():
    policy = rules()
    policy["rules"].append(
        {"id": "bis_overlap", "source": "BIS", "dataset": "other", "status": "allowed"}
    )
    ambiguous = Policy(policy)
    for value in [row(), row("Derived", audit={}), row(source_url=""), row(source_series_id="")]:
        kept, cells, _ = filter_rows([value], ambiguous, "cleared")
        assert not kept
        assert cells[("USA", "policy_rate")]["excluded_observations"] == 1


def test_wdi_profile_permission_does_not_authorise_pink_sheet_or_unreviewed_wdi():
    profile = row(
        "WorldBank",
        concept_id=None,
        profile_id="population",
        source_series_id="SP.POP.TOTL",
        source_url="https://api.worldbank.org/v2/country/USA/indicator/SP.POP.TOTL?source=2",
    )
    pink = row(
        "WorldBank",
        concept_id="oil_brent",
        source_series_id="PinkSheet/Monthly Prices/Brent",
        source_url="https://thedocs.worldbank.org/monthly.xlsx",
    )
    unknown = {**profile, "source_series_id": "NOT.REVIEWED"}
    kept, cells, _ = filter_rows([profile, pink, unknown], Policy(rules()), "cleared")
    assert len(kept) == 1 and kept[0]["profile_id"] == "population"
    assert "UN Population" in kept[0]["attribution"]
    assert "https://creativecommons.org/licenses/by/4.0/" in kept[0]["terms_urls"]
    assert "https://data.worldbank.org/summary-terms-of-use" in kept[0]["terms_urls"]
    assert cells[("USA", "oil_brent")]["excluded_observations"] == 1
    assert cells[("USA", "population")]["excluded_observations"] == 1


def test_global_variant_is_filtered_by_its_dataset_policy():
    energy = row(
        "WorldBank",
        country="GLOBAL",
        concept_id="commod_idx",
        variant="energy",
        source_series_id="PinkSheet/Monthly Indices/Energy",
    )
    kept, cells, _ = filter_rows([energy], Policy(rules()), "cleared")
    assert not kept and cells[("GLOBAL", "commod_idx")]["excluded_observations"] == 1


def test_all_mode_is_explicit_and_preserves_values_with_uncleared_labels():
    inputs = [row(), row("OECD", "2000-Q2")]
    kept, cells, _ = filter_rows(inputs, Policy(rules()), "all")
    assert [item["value"] for item in kept] == [item["value"] for item in inputs]
    assert cells[("USA", "policy_rate")]["excluded_observations"] == 0
    assert "local-only" in kept[1]["terms_status"]
    with pytest.raises(ValueError, match="mode"):
        filter_rows(inputs, Policy(rules()), "anything")


def test_country_notes_and_raw_paths_cannot_enter_candidate_metadata():
    original = {
        "iso3": "USA",
        "name": "United States",
        "notes": [{"status": "DRAFT", "text": "Do not publish me"}],
        "membership_raw_path": "data/raw/source.bin",
    }
    result = MODULE["safe_country"](original)
    assert result["notes"] == [] and result["notes_status"] == "withheld_pending_review"
    assert "raw_path" not in json.dumps(result)
    assert original["notes"][0]["text"] == "Do not publish me"


def test_corrupted_or_outside_snapshot_file_is_rejected(tmp_path):
    path = tmp_path / "series.parquet"
    path.write_bytes(b"accepted")
    manifest = {"files": {"series.parquet": {"sha256": MODULE["digest"](b"accepted"), "bytes": 8}}}
    assert MODULE["verified_file"](tmp_path, manifest, "series.parquet") == path
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum"):
        MODULE["verified_file"](tmp_path, manifest, "series.parquet")


def test_size_accounting_reconciles_payload_and_shared_overhead(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/file.json").write_bytes(b"1234567890")
    (tmp_path / "index.html").write_bytes(b"12345")
    result = MODULE["size_report"](tmp_path, {"bis": {"value_payload_bytes": 7}})
    assert result["total_bytes"] == 15
    assert result["value_payload_bytes"] + result["other_bytes"] == 15


def test_missing_input_explains_confirmed_publication_exclusion_without_changing_other_blocks():
    cfg = {
        "frequency": "Q",
        "sample": {"start": "1999-Q1", "end": "latest"},
        "aggregation": {},
        "special_periods": {"covid": "include"},
        "series": [{"concept_id": "gdp", "role": "dependent", "transform": "level"}],
    }
    publication = {
        "excluded_observations": 20,
        "retained_observations": 0,
        "excluded_sources": [{"id": "oecd", "status": "unclear"}],
    }
    card = {"concept_id": "gdp", "status": "missing", "publication": publication}
    bundle = {
        "snapshot_id": "synthetic",
        "countries": {
            "USA": {
                "metadata": {"iso3": "USA"},
                "series": {"gdp": {"metadata": card, "observations": []}},
            }
        },
    }
    data, checks = prepare_country(cfg, bundle, "USA")
    missing = next(item for item in checks if item["code"] == "missing_coverage")
    assert data.frame.empty and missing["level"] == "block"
    assert "not included in this publication candidate" in missing["message"]
    assert missing["publication"] == publication
    card.pop("publication")
    _, checks = prepare_country(cfg, bundle, "USA")
    missing = next(item for item in checks if item["code"] == "missing_coverage")
    assert missing["message"] == "No data for gdp in USA; remove it or choose another indicator."
    assert "publication" not in missing
