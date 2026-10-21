"""Synthetic end-to-end data invariants, including independent raw provenance checks."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from macrolab.data.audit import SourceAudit, audit_data
from macrolab.data.coverage import build_coverage
from macrolab.data.harmonise import derive_term_spread, harmonise, splice_policy_rates
from macrolab.data.snapshot import SnapshotClient, SnapshotError, verify_raw_manifest
from macrolab.data.sources.http import FetchRecord, SourceClient
from macrolab.data.standardise import standardise
from macrolab.data.validate import validate

COUNTRIES = [{"iso3": "USA", "name": "United States", "eu_member": False}]
RULES = {
    "requested_sample_start": "2026-01-01",
    "adequate_history": {"M": 3, "Q": 3, "A": 3},
    "plausibility": {"unemp": [0, 100]},
    "elb_threshold_percent": 0.25,
    "staleness_months": {"M": 6, "Q": 9, "A": 24},
    "commodity_staleness_months": 3,
}


def observation(
    period: str,
    value: float,
    *,
    concept: str = "unemp",
    source: str = "OECD",
    country: str = "USA",
    series: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "country": country,
        "concept_id": concept,
        "source": source,
        "source_series_id": series or f"{source}/{country}/{concept}",
        "date": period,
        "value": value,
        "unit": "percent",
        "unit_mult": 0,
        "sa_flag": "SA",
        "price_basis": "not_applicable",
        "base_year": None,
        "freq": "M",
        "obs_status": "reported",
        "source_url": "https://sdmx.oecd.org/synthetic",
        "attribution": "Synthetic test fixture",
        "flags": [],
        **extra,
    }


def definition(concept: str = "unemp", *, scope: str = "national") -> dict[str, Any]:
    return {
        "concept_id": concept,
        "title": concept,
        "scope": scope,
        "native_frequency": "M",
        "default_transform": "level",
        "source_priority": ["OECD", "Eurostat"],
    }


def test_first_adequate_source_wins_without_filling_its_gaps_from_fallback() -> None:
    preferred = [observation(f"2026-{month:02d}", month) for month in (1, 3, 4)]
    fallback = [
        observation(f"2026-{month:02d}", 40 + month, source="Eurostat") for month in range(1, 7)
    ]
    selected, losing, _ledger, issues = harmonise(
        preferred + fallback, COUNTRIES, [definition()], RULES
    )
    assert {(row["date"], row["source"]) for row in selected} == {
        ("2026-01", "OECD"),
        ("2026-03", "OECD"),
        ("2026-04", "OECD"),
    }
    assert len(losing) == len(fallback)
    assert not issues


def test_fallback_is_selected_when_preferred_history_is_inadequate() -> None:
    rows = [observation("2026-01", 1)] + [
        observation(f"2026-{month:02d}", month, source="Eurostat") for month in (1, 2, 3)
    ]
    selected, _losing, ledger, _issues = harmonise(rows, COUNTRIES, [definition()], RULES)
    assert {row["source"] for row in selected} == {"Eurostat"}
    assert ledger[0]["fallback"] is True


def test_when_all_sources_are_short_the_configured_longest_available_rule_applies() -> None:
    rows = [observation("2026-01", 1)] + [
        observation(f"2026-{month:02d}", month, source="Eurostat") for month in (1, 2)
    ]
    selected, _losing, _ledger, _issues = harmonise(rows, COUNTRIES, [definition()], RULES)
    assert len(selected) == 2
    assert {row["source"] for row in selected} == {"Eurostat"}


def test_validation_preserves_missing_months_and_extreme_source_values() -> None:
    source = [observation("2026M01", 10), observation("2026M03", 500)]
    rows, issues = standardise(source)
    assert not issues
    result = validate(rows, RULES)
    coverage, cards = build_coverage(rows, COUNTRIES, [definition()], RULES, date(2026, 4, 1), [])
    assert [(row["date"], row["value"]) for row in rows] == [("2026-01", 10), ("2026-03", 500)]
    assert result["interpolated_observations"] == 0
    assert result["gaps"][0]["missing_periods"] == 1
    assert "plausibility_outlier" in rows[-1]["flags"]
    assert coverage[0]["missing_periods"] == 1
    assert "internal_gaps" in cards[0]["warnings"]


def test_available_sample_start_is_an_observed_period_not_a_gap() -> None:
    rows = [observation("2025-12", 10), observation("2026-03", 12)]
    coverage, cards = build_coverage(rows, COUNTRIES, [definition()], RULES, date(2026, 4, 1), [])
    assert coverage[0]["requested_sample_start"] == "2026-01-01"
    assert coverage[0]["actual_available_start"] == "2026-03-01"
    assert cards[0]["actual_available_start"] == "2026-03-01"


def test_fractional_unit_multiplier_is_rejected_without_silent_truncation() -> None:
    rows, issues = standardise([observation("2026-01", 10, unit_mult=1.5)])
    assert rows == []
    assert issues and issues[0]["code"] == "schema_rejection"


def test_euro_splice_retains_national_history_and_never_fills_ecb_gaps() -> None:
    countries = [{"iso3": "GRC", "euro_adoption": "2001-01-01"}, {"iso3": "EA"}]
    rows = [
        observation("2000-12", 6, concept="policy_rate", country="GRC", source="BIS"),
        observation("2001-01", 7, concept="policy_rate", country="GRC", source="BIS"),
        observation("2001-03", 8, concept="policy_rate", country="GRC", source="BIS"),
        observation("2000-12", 4, concept="policy_rate", country="EA", source="ECB"),
        observation("2001-01", 4.25, concept="policy_rate", country="EA", source="ECB"),
        observation("2001-02", 4.5, concept="policy_rate", country="EA", source="ECB"),
    ]
    spliced, issues = splice_policy_rates(rows, countries)
    greek = {row["date"]: row for row in spliced if row["country"] == "GRC"}
    assert not issues
    assert {key: row["value"] for key, row in greek.items()} == {
        "2000-12": 6,
        "2001-01": 4.25,
        "2001-02": 4.5,
    }
    assert greek["2001-01"]["source_country"] == "EA"
    assert greek["2001-01"]["shared"] is True
    assert "euro_adoption_break" in greek["2001-01"]["flags"]


def test_term_spread_uses_only_matching_dates_and_compatible_scaling() -> None:
    rows = [
        observation("2026-01", 5, concept="rate_10y"),
        observation("2026-01", 2, concept="rate_3m"),
        observation("2026-02", 2, concept="rate_3m"),
        observation("2026-03", 5, concept="rate_10y", unit_mult=3),
        observation("2026-03", 2, concept="rate_3m", unit_mult=0),
    ]
    spread = derive_term_spread(rows)
    assert [(row["date"], row["value"]) for row in spread] == [("2026-01", 3)]
    assert spread[0]["unit"] == "percentage points"
    assert len(spread[0]["audit"]["components"]) == 2


def write_snapshot(root: Path) -> tuple[str, str, str]:
    snapshot = "20261020-2359"
    raw = root / "data/raw/OECD" / snapshot / "synthetic.bin"
    raw.parent.mkdir(parents=True)
    body = b"TIME_PERIOD,OBS_VALUE\n2026-01,1.0\n"
    raw.write_bytes(body)
    url = "https://sdmx.oecd.org/synthetic"
    record = FetchRecord(
        "OECD",
        "fixture",
        snapshot,
        1,
        url,
        url,
        "2026-10-20T20:00:00+00:00",
        200,
        "text/csv",
        hashlib.sha256(body).hexdigest(),
        len(body),
        str(raw.relative_to(root)),
        True,
        0.0,
        None,
    )
    manifest = root / "data/manifests/raw_manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(asdict(record)) + "\n")
    return snapshot, url, str(raw.relative_to(root))


def test_offline_replay_never_fetches_or_changes_raw_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot, url, raw_path = write_snapshot(tmp_path)

    def fail_network(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("Offline replay attempted an external request")

    monkeypatch.setattr(SourceClient, "_attempt", fail_network)
    manifest_path = tmp_path / "data/manifests/raw_manifest.jsonl"
    original_manifest = manifest_path.read_bytes()
    client = SnapshotClient(tmp_path, snapshot, offline=True, as_of_date=date(2026, 10, 20))
    replay = client.fetch("OECD", "fixture", url, "text/csv")
    assert replay.body == (tmp_path / raw_path).read_bytes()
    with pytest.raises(SnapshotError, match="no recorded request"):
        client.fetch("OECD", "missing", url, "text/csv")
    assert manifest_path.read_bytes() == original_manifest
    assert verify_raw_manifest(tmp_path, snapshot)["response_hashes_verified"] == 1


def test_offline_replay_rejects_changed_raw_bytes(tmp_path: Path) -> None:
    snapshot, url, raw_path = write_snapshot(tmp_path)
    (tmp_path / raw_path).write_bytes(b"TIME_PERIOD,OBS_VALUE\n2026-01,9.0\n")
    client = SnapshotClient(tmp_path, snapshot, offline=True)
    with pytest.raises(SnapshotError, match="checksum mismatch"):
        client.fetch("OECD", "fixture", url, "text/csv")


def test_independent_audit_detects_a_changed_tidy_value(tmp_path: Path) -> None:
    path = tmp_path / "data/raw/OECD/synthetic.csv"
    path.parent.mkdir(parents=True)
    lines = ["COUNTRY,TIME_PERIOD,OBS_VALUE"]
    rows = []
    for country in ("USA", "DEU", "JPN"):
        for month in (1, 2, 3):
            period = f"2026-{month:02d}"
            lines.append(f"{country},{period},{month}")
            rows.append(
                observation(
                    period,
                    month,
                    country=country,
                    raw_path=str(path.relative_to(tmp_path)),
                    audit={
                        "parser": "csv",
                        "source_period": period,
                        "selector": {"COUNTRY": country},
                    },
                )
            )
    path.write_text("\n".join(lines) + "\n")
    good = audit_data(tmp_path, rows, [definition()])
    assert good["passed"] is True
    changed = deepcopy(rows)
    changed[1]["value"] = 200
    bad = audit_data(tmp_path, changed, [definition()])
    assert bad["passed"] is False
    assert bad["mismatches"] == 1
    assert bad["matched"] == 8


def test_jsonstat_audit_rejects_wrong_date_even_when_the_numeric_cell_matches(
    tmp_path: Path,
) -> None:
    path = tmp_path / "data/raw/Eurostat/synthetic.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "id": ["geo", "time"],
                "size": [1, 2],
                "value": {"0": 10, "1": 11},
                "dimension": {
                    "geo": {"category": {"index": {"DE": 0}}},
                    "time": {"category": {"index": {"2026-01": 0, "2026-02": 1}}},
                },
            }
        )
    )
    wrong = observation(
        "2026-02",
        10,
        country="DEU",
        source="Eurostat",
        raw_path=str(path.relative_to(tmp_path)),
        audit={
            "parser": "jsonstat",
            "source_period": "2026-02",
            "selector": {"geo": "DE"},
            "flat_index": 0,
        },
    )
    with pytest.raises(ValueError):
        SourceAudit(tmp_path).reference_value(wrong)


def test_wdi_audit_rejects_wrong_raw_period_pointer(tmp_path: Path) -> None:
    path = tmp_path / "data/raw/WorldBank/synthetic.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            [
                {"pages": 1},
                [
                    {
                        "date": "2024",
                        "countryiso3code": "USA",
                        "indicator": {"id": "SP.POP.TOTL"},
                        "value": 100,
                    }
                ],
            ]
        )
    )
    wrong = observation(
        "2025",
        100,
        source="WorldBank",
        freq="A",
        source_series_id="SP.POP.TOTL",
        raw_path=str(path.relative_to(tmp_path)),
        audit={
            "format": "wdi-json",
            "source_period": "2025",
            "json_pointer": "/1/0/value",
            "source_country": "USA",
            "indicator": "SP.POP.TOTL",
        },
    )
    with pytest.raises(ValueError):
        SourceAudit(tmp_path).reference_value(wrong)


def test_stale_global_commodity_produces_visible_country_card_warning() -> None:
    global_row = observation(
        "2026-06",
        80,
        concept="oil_brent",
        source="WorldBank",
        country="GLOBAL",
        unit="USD/bbl",
        flags=["stale_source"],
    )
    concept = definition("oil_brent", scope="global")
    concept["source_priority"] = ["World Bank Pink Sheet"]
    rows, _losing, _ledger, _issues = harmonise([global_row], COUNTRIES, [concept], RULES)
    coverage, cards = build_coverage(rows, COUNTRIES, [concept], RULES, date(2026, 10, 20), [])
    assert rows[0]["source_country"] == "GLOBAL"
    assert rows[0]["shared"] is True
    assert coverage[0]["stale"] is True
    assert coverage[0]["status"] == "limited"
    assert "stale" in cards[0]["warnings"]
    assert "stale_source" in cards[0]["warnings"]
