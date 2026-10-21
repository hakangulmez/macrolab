"""Synthetic offline checks for source dimensions, native observations and audit coordinates."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from macrolab.data.sources.bis import fetch_bis, read_sdmx
from macrolab.data.sources.eurostat import jsonstat_observations, normalise_eurostat, specifications
from macrolab.data.sources.imf import normalise_imf


def response(body: bytes = b"") -> Any:
    return SimpleNamespace(
        body=body,
        record=SimpleNamespace(
            status=200,
            url="https://example.invalid/synthetic-fixture",
            error=None,
            raw_path="data/raw/synthetic-fixture.bin",
            retrieved_utc="2000-01-01T00:00:00+00:00",
        ),
    )


def test_bis_xml_merges_only_matching_group_and_dataset_attributes() -> None:
    body = b"""<Data><DataSet UNIT_MULT="0">
    <Group EER_TYPE="R" REF_AREA="US" UNIT_MEASURE="882"/>
    <Group EER_TYPE="R" REF_AREA="JP" UNIT_MEASURE="628"/>
    <Series FREQ="M" EER_TYPE="R" EER_BASKET="B" REF_AREA="US">
    <Obs TIME_PERIOD="2000-01" OBS_VALUE="100"/></Series></DataSet></Data>"""
    rows, parser = read_sdmx(body)
    assert parser == "sdmx_xml"
    assert rows[0]["UNIT_MEASURE"] == "882"
    assert rows[0]["UNIT_MULT"] == "0"


class FixtureClient:
    def fetch(self, source: str, request_id: str, url: str, accept: str) -> Any:
        bodies = {
            "bis_policy_rate": b"""<Data><DataSet UNIT_MULT="0" UNIT_MEASURE="368">
                <Series FREQ="M" REF_AREA="US"><Obs TIME_PERIOD="2000-01" OBS_VALUE="5"/></Series>
                <Series FREQ="M" REF_AREA="DE"><Obs TIME_PERIOD="1998-12" OBS_VALUE="3"/></Series>
                <Series FREQ="M" REF_AREA="XM"><Obs TIME_PERIOD="2000-01" OBS_VALUE="4"/></Series>
                </DataSet></Data>""",
            "bis_house_real": b"""<Data><DataSet UNIT_MULT="0">
                <Series FREQ="Q" REF_AREA="US" VALUE="R" UNIT_MEASURE="628">
                <Obs TIME_PERIOD="2000-Q1" OBS_VALUE="100"/></Series>
                <Series FREQ="Q" REF_AREA="US" VALUE="R" UNIT_MEASURE="771">
                <Obs TIME_PERIOD="2000-Q1" OBS_VALUE="9"/></Series></DataSet></Data>""",
        }
        return response(bodies.get(request_id, b"<Data><DataSet/></Data>"))


def test_bis_keeps_raw_national_rate_and_global_us_copy() -> None:
    result = fetch_bis(
        FixtureClient(),
        [
            {"iso3": "USA", "iso2": "US"},
            {"iso3": "DEU", "iso2": "DE"},
            {"iso3": "EA", "iso2": None},
        ],
    )  # type: ignore[arg-type]
    rates = {
        (r["country"], r["concept_id"]): r
        for r in result["rows"]
        if "policy_rate" in r["concept_id"]
    }
    assert rates[("DEU", "policy_rate")]["date"] == "1998-12"
    assert rates[("EA", "policy_rate")]["value"] == 4
    assert rates[("GLOBAL", "us_policy_rate")]["value"] == rates[("USA", "policy_rate")]["value"]
    assert rates[("USA", "policy_rate")]["audit"]["selector"]["REF_AREA"] == "US"
    assert "monthly_end_of_period" in rates[("USA", "policy_rate")]["flags"]


def test_house_index_never_accepts_growth_rate_as_level() -> None:
    result = fetch_bis(FixtureClient(), [{"iso3": "USA", "iso2": "US"}])  # type: ignore[arg-type]
    house = [row for row in result["rows"] if row["concept_id"] == "house_real"]
    assert len(house) == 1
    assert house[0]["value"] == 100
    assert house[0]["base_year"] == "2010"


def jsonstat_fixture() -> dict[str, Any]:
    return {
        "id": ["freq", "geo", "time"],
        "size": [1, 2, 2],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}, "label": {"M": "Monthly"}}},
            "geo": {
                "category": {
                    "index": {"DE": 0, "EA20": 1},
                    "label": {"DE": "Germany", "EA20": "Euro area20"},
                }
            },
            "time": {
                "category": {
                    "index": {"2000-01": 0, "2000-02": 1},
                    "label": {"2000-01": "2000-01", "2000-02": "2000-02"},
                }
            },
        },
        "value": {"0": 100, "3": 102},
        "status": {"3": "p"},
    }


def test_jsonstat_sparse_flat_index_and_status() -> None:
    obs = jsonstat_observations(jsonstat_fixture())
    assert obs[1] == (3, {"freq": "M", "geo": "EA20", "time": "2000-02"}, 102.0, "p")


def test_jsonstat_out_of_bounds_rejected() -> None:
    payload = jsonstat_fixture()
    payload["value"] = {"4": 10}
    with pytest.raises(ValueError, match="exceeds"):
        jsonstat_observations(payload)


def test_eurostat_preserves_audit_index_and_flags_composition() -> None:
    spec = specifications()[0]
    rows = normalise_eurostat(
        jsonstat_fixture(),
        response(),
        [{"iso3": "DEU", "iso2": "DE"}, {"iso3": "EA", "iso2": None}],
        spec,
    )
    ea = next(row for row in rows if row["country"] == "EA")
    assert ea["audit"]["flat_index"] == 3
    assert ea["source_geo"] == "EA20"
    assert "euro_area_composition_mismatch" in ea["flags"]
    assert ea["sa_flag"] == "NSA"
    assert ea["base_year"] == "2025"


def test_current_hicp_uses_new_classification_and_index_unit() -> None:
    headline, core = specifications()[:2]
    assert headline["dataset"] == core["dataset"] == "prc_hicp_minr"
    assert headline["filters"] == {"unit": "I25", "coicop18": "TOTAL"}
    assert core["filters"]["coicop18"] == "TOT_X_NRG_FOOD"
    assert "excludes_energy_food_alcohol_tobacco" in core["flags"]


def test_imf_omits_forecasts_using_source_actual_boundary() -> None:
    body = (
        b"COUNTRY,INDICATOR,FREQUENCY,TIME_PERIOD,OBS_VALUE,UNIT,SCALE,SERIES_NAME,LATEST_ACTUAL_ANNUAL_DATA\n"
        b"USA,GGXWDG_NGDP,A,2024,100,PT,0,General government debt Percent of GDP,2024\n"
        b"USA,GGXWDG_NGDP,A,2025,110,PT,0,General government debt Percent of GDP,2024\n"
    )
    rows, issues = normalise_imf(body, response(body), {"USA"}, "fiscal")
    assert len(rows) == 1
    assert rows[0]["date"] == "2024"
    assert rows[0]["audit"]["actual_year_cutoff"] == 2024
    assert issues == []


def test_imf_missing_actual_boundary_is_explicit_missingness() -> None:
    body = (
        b"COUNTRY,INDICATOR,FREQUENCY,TIME_PERIOD,OBS_VALUE,UNIT,SERIES_NAME,LATEST_ACTUAL_ANNUAL_DATA\n"
        b"USA,GGXWDG_NGDP,A,2024,100,PT,General government debt Percent of GDP,\n"
    )
    rows, issues = normalise_imf(body, response(body), {"USA"}, "fiscal")
    assert rows == []
    assert issues[0]["code"] == "actual_boundary_unavailable"


def test_imf_fx_preserves_monthly_average_and_raw_period() -> None:
    body = (
        b"COUNTRY,INDICATOR,TYPE_OF_TRANSFORMATION,FREQUENCY,TIME_PERIOD,OBS_VALUE,SCALE\n"
        b"CAN,XDC_USD,PA_RT,M,2000-M01,1.5,0\n"
        b"CAN,XDC_USD,EOP_RT,M,2000-M01,1.6,0\n"
    )
    rows, _ = normalise_imf(body, response(body), {"CAN"}, "fx")
    assert len(rows) == 1
    assert rows[0]["date"] == "2000-01"
    assert rows[0]["audit"]["source_period"] == "2000-M01"
    assert rows[0]["value"] == 1.5
