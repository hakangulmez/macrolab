"""G1.1 replaces authorised vintages while retaining the accepted baseline intact."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from macrolab.data import correction, pipeline
from macrolab.data.pipeline import canonical_hash, write_parquet
from macrolab.data.snapshot import SnapshotError, sha256_file

AS_OF = date(2026, 10, 20)
RULES = {
    "as_of_date": AS_OF.isoformat(),
    "requested_sample_start": "2026-01-01",
    "adequate_history": {"M": 1, "Q": 1, "A": 1},
    "staleness_months": {"M": 6, "Q": 9, "A": 24},
    "commodity_staleness_months": 3,
}
CONCEPTS = [
    {
        "concept_id": concept,
        "title": concept,
        "scope": "national",
        "native_frequency": "M",
        "default_transform": "level",
        "source_priority": ["OECD", "Eurostat"],
    }
    for concept in ("cpi", "cli", "unemp", "conf_cons")
]


def observation(concept: str, period: str, value: float, **changes: Any) -> dict[str, Any]:
    return {
        "country": "USA",
        "concept_id": concept,
        "source": "OECD",
        "source_series_id": f"synthetic/USA/{concept}",
        "date": period,
        "value": value,
        "unit": "IX",
        "unit_mult": 0,
        "sa_flag": "SA",
        "price_basis": "index",
        "base_year": "2015",
        "freq": "M",
        "obs_status": "reported",
        "shared": False,
        "source_url": "https://sdmx.oecd.org/synthetic-correction-fixture",
        "attribution": "Synthetic test fixture",
        "terms_status": "local only",
        "flags": ["baseline_flag"],
        "audit": {"parser": "csv", "source_period": period},
        **changes,
    }


@pytest.fixture
def baseline(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Path, Path, Mock]]:
    # Keep even temporary test artefacts inside the authorised project directory.
    runs = Path(__file__).resolve().parents[2] / "runs"
    runs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="test-g11-correction-", dir=runs) as directory:
        root = Path(directory)
        base = root / "data/processed/snapshots/base"
        base.mkdir(parents=True)
        selected = [
            observation("cpi", "2026-01", 100),
            observation("cpi", "2026-02", 101),
            observation("cli", "2026-01", 95),
            observation("cli", "2026-02", 96),
            observation("unemp", "2026-01", 5),
            observation("unemp", "2026-02", 5.5),
            observation("conf_cons", "2026-01", 99.8),
        ]
        losing = [
            observation("cpi", "2026-04", 777, selection_status="not_selected"),
            observation(
                "unemp", "2026-01", 123, source="Eurostat", selection_status="not_selected"
            ),
        ]
        for name, rows in {
            "series.parquet": selected,
            "candidate_series.parquet": losing,
            "variant_series.parquet": [{"variant": "frozen", "value": 42.5}],
            "profiles.parquet": [{"country": "USA", "profile": "population", "value": 123.0}],
        }.items():
            write_parquet(base / name, rows)
        for name, value in {
            "countries.json": [{"iso3": "USA", "name": "United States", "eu_member": False}],
            "issues.json": [
                {"concept_id": "cpi", "code": "old_price_issue"},
                {"concept_id": "unemp", "code": "keep_this_issue"},
            ],
            "selection_ledger.json": [
                {"concept_id": "cpi", "selected_source": "OECD"},
                {"concept_id": "unemp", "selected_source": "OECD"},
            ],
            "source_details.json": {"source": "synthetic verified baseline"},
        }.items():
            (base / name).write_text(json.dumps(value))
        files = {path.name: {"sha256": sha256_file(path)} for path in base.iterdir()}
        (base / "processed_manifest.json").write_text(
            json.dumps(
                {
                    "snapshot_id": "base",
                    "validation_passed": True,
                    "audit_summary": {"passed": True},
                    "files": files,
                }
            )
        )
        verified_raw = Mock(return_value={"request_records": 1, "response_hashes_verified": 1})
        monkeypatch.setattr(correction, "verify_raw_manifest", verified_raw)
        yield root, base, verified_raw


def prepare(root: Path, base: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return correction.prepare(
        root,
        base,
        {"rows": rows, "issues": []},
        {"rows": [observation("cli", "2026-03", 102, source_series_id="synthetic/current-cli")]},
        deepcopy(CONCEPTS),
        deepcopy(RULES),
        AS_OF,
    )


def test_latest_requested_vintage_replaces_old_history_without_mutating_other_data(
    baseline: tuple[Path, Path, Mock],
) -> None:
    root, base, verified_raw = baseline
    checksums = {path.name: sha256_file(path) for path in base.iterdir()}
    before = correction.read_rows(base / "series.parquet")
    untouched = [row for row in before if row["concept_id"] not in correction.TARGETS]
    incoming = [observation("cpi", "2026-01", 200), observation("cpi", "2026-03", 220)]
    original_input = deepcopy(incoming)

    result = prepare(root, base, incoming)

    selected = result["prepared_selection"]["selected"]
    assert [(row["date"], row["value"]) for row in selected if row["concept_id"] == "cpi"] == [
        ("2026-01", 200),
        ("2026-03", 220),
    ]  # Neither an omitted old month nor a prior losing vintage can be spliced back.
    cli_rows = [row for row in selected if row["concept_id"] == "cli"]
    assert len(cli_rows) == 1 and cli_rows[0]["source_series_id"] == "synthetic/current-cli"
    actual_untouched = [row for row in selected if row["concept_id"] not in correction.TARGETS]
    assert actual_untouched == sorted(untouched, key=correction.row_order)
    assert result["unchanged_proof"]["before_hash"] == canonical_hash(actual_untouched)
    assert (
        result["unchanged_proof"]["passed"] is False
    )  # publish must independently finish the proof.
    assert result["profiles"] == correction.read_rows(base / "profiles.parquet")
    assert result["variant_rows"] == correction.read_rows(base / "variant_series.parquet")
    assert result["countries"] == json.loads((base / "countries.json").read_text())
    assert incoming == original_input
    assert {path.name: sha256_file(path) for path in base.iterdir()} == checksums
    assert {issue["code"] for issue in result["issues"]} == {"keep_this_issue"}
    assert any(row["concept_id"] == "unemp" for row in result["prepared_selection"]["losing"])
    verified_raw.assert_called_once_with(root, "base")


@pytest.mark.parametrize(
    "encoded_flags", ['"not-a-list"', '{"stale":true}', "[1]", '["unterminated"']
)
def test_malformed_serialised_flags_are_rejected(
    baseline: tuple[Path, Path, Mock],
    encoded_flags: str,
) -> None:
    _root, base, _verified_raw = baseline
    path = base / "malformed-flags.parquet"
    write_parquet(path, [observation("cpi", "2026-01", 123, flags=encoded_flags)])
    with pytest.raises(ValueError):
        correction.read_rows(path)


def test_correction_rejects_other_concept_rows_before_selection(
    baseline: tuple[Path, Path, Mock],
) -> None:
    root, base, _verified_raw = baseline
    original = sha256_file(base / "series.parquet")
    with pytest.raises(SnapshotError, match="authorized concept scope"):
        prepare(root, base, [observation("unemp", "2026-03", 99)])
    assert sha256_file(base / "series.parquet") == original


def test_correction_rejects_changed_baseline_files_before_reading_rows(
    baseline: tuple[Path, Path, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, base, verified_raw = baseline
    with (base / "countries.json").open("a") as handle:
        handle.write(" ")  # Still valid JSON; the accepted byte-level checksum must detect it.
    read = Mock(side_effect=AssertionError("Unverified baseline rows must not be read"))
    monkeypatch.setattr(correction, "read_rows", read)
    with pytest.raises(SnapshotError, match="Baseline output checksum mismatch: countries.json"):
        prepare(root, base, [observation("cpi", "2026-03", 220)])
    read.assert_not_called()
    verified_raw.assert_not_called()


@pytest.mark.parametrize("include_g11", [False, True])
def test_collect_corrections_preserve_unrelated_sources_and_historical_default(
    monkeypatch: pytest.MonkeyPatch, include_g11: bool
) -> None:
    client = Mock(offline=True)
    countries = [{"iso3": "USA", "name": "United States"}]
    monkeypatch.setattr(pipeline, "fetch_countries", Mock(return_value=countries))
    monkeypatch.setattr(pipeline, "enrich_country_metadata", lambda countries, client: countries)
    old_cli = observation("cli", "2026-01", 95)
    old_cpi = observation("cpi", "2026-01", 100)
    unrelated = observation("unemp", "2026-01", 5)
    profile = {"country": "USA", "profile": "population", "value": 123.0}
    variant = {"variant": "frozen", "value": 42.5}
    old_cli_issue = {"concept_id": "cli", "code": "historical_cli_issue"}
    unrelated_issue = {"concept_id": "unemp", "code": "preserved_issue"}
    for source in ("oecd", "bis", "imf", "ecb", "eurostat", "worldbank"):
        response: dict[str, Any] = {"rows": []}
        if source == "oecd":
            response = {"rows": [old_cli, old_cpi], "issues": [old_cli_issue]}
        elif source == "worldbank":
            response = {
                "rows": [unrelated],
                "profiles": [profile],
                "variant_rows": [variant],
                "issues": [unrelated_issue],
            }
        monkeypatch.setattr(pipeline, f"fetch_{source}", Mock(return_value=response))
    new_cli = observation("cli", "2026-03", 102, source_series_id="synthetic/current-cli")
    new_cpi = observation("cpi", "2026-03", 220, source_series_id="synthetic/current-cpi")
    prices = Mock(return_value={"rows": [new_cpi]})
    cli = Mock(return_value={"rows": [new_cli]})
    monkeypatch.setattr(pipeline, "fetch_prices", prices)
    monkeypatch.setattr(pipeline, "fetch_cli", cli)

    result = pipeline.collect(client, include_g11=True) if include_g11 else pipeline.collect(client)

    assert unrelated in result["rows"]
    assert result["profiles"] == [profile]
    assert result["variant_rows"] == [variant]
    assert unrelated_issue in result["issues"]
    if include_g11:
        assert result["rows"] == [old_cpi, unrelated, new_cpi, new_cli]
        assert old_cli_issue not in result["issues"]
        prices.assert_called_once_with(client, countries)
        cli.assert_called_once_with(client, countries)
    else:
        assert result["rows"] == [old_cli, old_cpi, unrelated]
        assert old_cli_issue in result["issues"]
        prices.assert_not_called()
        cli.assert_not_called()
