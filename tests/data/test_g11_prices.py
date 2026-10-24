"""Offline price-refresh checks: definition boundaries and exact raw audit locations."""

from __future__ import annotations

import csv
import io
from typing import Any, cast

import pytest

from macrolab.data.sources.g11_prices import (
    configuration,
    cpi_mappings,
    fetch_prices,
    normalise_ppi_eurostat,
)
from macrolab.data.sources.http import FetchRecord, FetchResult, SourceClient
from macrolab.data.sources.oecd import standardise_csv


def fetched(body: bytes = b"fixture", *, complete: bool = True) -> FetchResult:
    return FetchResult(
        body,
        FetchRecord(
            source="fixture",
            probe_id="fixture",
            snapshot_id="fixture",
            attempt=1,
            url="https://ec.europa.eu/eurostat/fixture",
            final_url=None,
            retrieved_utc="2026-10-20T10:00:00Z",
            status=200,
            mime_type="text/csv",
            sha256="a" * 64,
            size_bytes=len(body),
            raw_path="data/raw/fixture.bin",
            body_complete=complete,
            elapsed_seconds=0,
            error=None,
        ),
    )


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode()


def test_current_cpi_keeps_hicp_core_and_national_core_distinct() -> None:
    config = configuration()["oecd_cpi"]
    dims = config["dimensions"]
    observations = []
    for country, methodology, expenditure in [
        ("DEU", "N", "_TXCP01_NRG"),
        ("DEU", "HICP", "_TXNRG_01_02"),
        ("JPN", "N", "_TXCP01_NRG"),
        ("JPN", "HICP", "_TXNRG_01_02"),
        ("EA20", "N", "_T"),
        ("EA20", "HICP", "_T"),
    ]:
        observations.append(
            {
                "DATAFLOW": "COICOP2018",
                "REF_AREA": country,
                "FREQ": "M",
                "METHODOLOGY": methodology,
                "MEASURE": "CPI",
                "UNIT_MEASURE": "IX",
                "EXPENDITURE": expenditure,
                "ADJUSTMENT": "N",
                "TRANSFORMATION": "_Z",
                "TIME_PERIOD": "2026-08",
                "OBS_VALUE": "123.456",
                "UNIT_MULT": "0",
                "BASE_PER": "2015",
                "OBS_STATUS": "P",
            }
        )
    rows, issues = standardise_csv(
        csv_bytes(observations),
        config,
        cpi_mappings(),
        {"dimensions": dims, "labels": {"UNIT_MEASURE": {"IX": "Index"}}},
        [
            {"iso3": "DEU", "eu_member": True},
            {"iso3": "JPN", "eu_member": False},
            {"iso3": "EA", "eu_member": False, "current_euro_area_code": "EA21"},
        ],
        source_url=config["data_url"],
        raw_path="data/raw/fixture.bin",
    )
    assert not issues
    assert {(r["country"], r["concept_id"]) for r in rows} == {
        ("DEU", "cpi_core"),
        ("JPN", "cpi_core"),
        ("EA", "cpi"),
    }
    assert all(r["value"] == 123.456 and r["base_year"] == "2015" for r in rows)
    assert all(set(r["audit"]["selector"]) == {"DATAFLOW", *dims} for r in rows)
    german = next(r for r in rows if r["country"] == "DEU")
    assert "HICP" in german["flags"]
    assert "excludes_energy_food_alcohol_tobacco" in german["flags"]
    assert "classification_COICOP2018" in german["flags"]


def ppi_payload() -> dict[str, Any]:
    codes = {**configuration()["eurostat_ppi"]["filters"], "geo": "DE", "time": "2026-08"}
    return {
        "id": list(codes),
        "size": [1] * len(codes),
        "value": {"0": 142.75},
        "status": {"0": "p"},
        "dimension": {
            key: {"category": {"index": {value: 0}, "label": {value: value}}}
            for key, value in codes.items()
        },
    }


def test_eurostat_ppi_retains_domestic_manufacturing_definition_and_audit() -> None:
    rows = normalise_ppi_eurostat(
        ppi_payload(),
        fetched(),
        [{"iso3": "DEU", "iso2": "DE", "eu_member": True}],
        configuration()["eurostat_ppi"],
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["value"] == 142.75 and row["base_year"] == "2021"
    assert row["freq"] == "M" and row["sa_flag"] == "NSA"
    assert row["market_scope"] == "domestic" and "manufacturing" in row["activity"]
    assert row["audit"]["selector"]["nace_r2"] == "C"
    assert row["audit"]["selector"]["indic_bt"] == "PRC_PRR_DOM"
    assert row["audit"]["flat_index"] == 0 and row["obs_status"] == "p"


@pytest.mark.parametrize(
    "country,geo,allowed",
    [("NOR", "NO", True), ("CHE", "CH", True), ("TUR", "TR", True), ("USA", "US", False)],
)
def test_g16_additional_ppi_scope_is_exact(country, geo, allowed):
    payload = ppi_payload()
    payload["dimension"]["geo"]["category"]["index"] = {geo: 0}
    rows = normalise_ppi_eurostat(
        payload,
        fetched(),
        [{"iso3": country, "iso2": geo, "eu_member": False}],
        configuration()["eurostat_ppi"],
    )
    assert bool(rows) == allowed


@pytest.mark.parametrize("dimension,code", [("unit", "I15"), ("nace_r2", "B-D"), ("s_adj", "SA")])
def test_eurostat_ppi_rejects_mislabelled_response(dimension: str, code: str) -> None:
    payload = ppi_payload()
    payload["dimension"][dimension]["category"]["index"] = {code: 0}
    with pytest.raises(ValueError, match="differs from verified selection"):
        normalise_ppi_eurostat(payload, fetched(), [], configuration()["eurostat_ppi"])


def test_incomplete_http_200_responses_do_not_create_price_mappings() -> None:
    class IncompleteClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def fetch(self, source: str, identifier: str, url: str, accept: str) -> FetchResult:
            self.calls.append(identifier)
            return fetched(complete=False)

    client = IncompleteClient()
    result = fetch_prices(cast(SourceClient, client), [{"iso3": "JPN", "eu_member": False}])
    assert result["rows"] == []
    assert len(client.calls) == 2  # No dependent data requests.
    assert len(
        [issue for issue in result["issues"] if issue["code"] == "source_request_unavailable"]
    ) == len(client.calls)


def test_historical_ppi_mapping_excludes_non_eu_countries_without_explicit_approval() -> None:
    payload = ppi_payload()
    payload["dimension"]["geo"]["category"] = {"index": {"CH": 0}, "label": {"CH": "Switzerland"}}
    rows = normalise_ppi_eurostat(
        payload,
        fetched(),
        [{"iso3": "CHE", "iso2": "CH", "eu_member": False}],
        {k: v for k, v in configuration()["eurostat_ppi"].items() if k != "additional_countries"},
    )
    assert rows == []
