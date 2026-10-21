"""Network-free tests for probe evidence, parsing and the access boundary."""

from __future__ import annotations

import hashlib
import io
import json
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from macrolab.data.sources.http import (
    CheckedRedirectHandler,
    NetworkBoundaryError,
    SourceClient,
    validate_url,
)
from macrolab.data.sources.parsers import (
    parse_csv,
    parse_eurostat,
    parse_pink_sheet,
    parse_sdmx_xml,
    parse_worldbank,
)
from macrolab.data.sources.probe import probe_one, public_evidence


@pytest.mark.parametrize(
    "url",
    [
        "http://api.worldbank.org/v2/country",
        "https://api.worldbank.org.evil.test/v2/country",
        "https://username:password@api.worldbank.org/v2/country",
        "https://api.worldbank.org:444/v2/country",
        "https://example.com/data.csv",
    ],
)
def test_rejects_nonapproved_urls(url: str) -> None:
    with pytest.raises(NetworkBoundaryError):
        validate_url(url)


def test_redirect_rechecks_host() -> None:
    handler = CheckedRedirectHandler()
    request = urllib.request.Request("https://api.worldbank.org/v2/country")
    with pytest.raises(NetworkBoundaryError):
        handler.redirect_request(request, None, 302, "Found", {}, "https://example.com/")


def test_csv_ignores_missing_and_nonfinite_values() -> None:
    parsed = parse_csv(
        b"observation_date,FEDFUNDS\n2024-01-01,5.33\n2024-02-01,.\n2024-03-01,NaN\n"
    )
    assert parsed["observation_count"] == 1
    assert parsed["example_observation"] == {"period": "2024-01-01", "value": 5.33}


def test_html_is_not_successful_csv() -> None:
    with pytest.raises(ValueError, match="date/value"):
        parse_csv(b"<html><title>Access denied</title></html>")


def test_sdmx_structure_specific_xml() -> None:
    parsed = parse_sdmx_xml(
        b'<Data><Series FREQ="M" REF_AREA="US" UNIT="PC">'
        b'<Obs TIME_PERIOD="2024-01" OBS_VALUE="5.3"/></Series></Data>'
    )
    assert parsed["observation_count"] == 1
    assert parsed["series_metadata"]["UNIT"] == "PC"


def test_sdmx_generic_xml() -> None:
    parsed = parse_sdmx_xml(
        b'<Data><Series><SeriesKey><Value id="REF_AREA" value="US"/></SeriesKey>'
        b'<Obs><ObsDimension value="2024-01"/><ObsValue value="5.3"/></Obs></Series></Data>'
    )
    assert parsed["first_period"] == "2024-01"
    assert parsed["series_metadata"]["REF_AREA"] == "US"


def test_worldbank_preserves_source_metadata() -> None:
    body = json.dumps(
        [
            {"sourceid": "2", "lastupdated": "2024-01-01"},
            [
                {
                    "indicator": {"id": "SP.POP.TOTL", "value": "Population"},
                    "country": {"id": "US", "value": "United States"},
                    "date": "2023",
                    "value": 100,
                    "unit": "",
                }
            ],
        ]
    ).encode()
    parsed = parse_worldbank(body)
    assert parsed["series_metadata"]["indicator"]["id"] == "SP.POP.TOTL"
    assert parsed["observation_count"] == 1


def test_eurostat_sparse_jsonstat() -> None:
    body = json.dumps(
        {
            "label": "Unemployment",
            "value": {"0": 3.1, "2": None},
            "dimension": {
                "time": {"category": {"label": {"2024-01": "2024-01", "2024-02": "2024-02"}}},
                "unit": {"category": {"label": {"PC_ACT": "% active"}}},
            },
        }
    ).encode()
    parsed = parse_eurostat(body)
    assert parsed["observation_count"] == 1
    assert parsed["series_metadata"]["dimensions"]["unit"]["label"]["PC_ACT"] == "% active"


def test_pink_sheet_extracts_named_column() -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Monthly Prices"
    sheet.append(["Synthetic test fixture"])
    sheet.append([None, "Crude oil, Brent"])
    sheet.append([None, "$/bbl"])
    sheet.append(["2024M01", 80.0])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    parsed = parse_pink_sheet(output.getvalue())
    assert parsed["observation_count"] == 1
    assert parsed["series_metadata"]["column"] == "Crude oil, Brent"


class FakeResponse(io.BytesIO):
    status = 200
    headers = {"Content-Type": "text/csv"}

    def geturl(self) -> str:
        return "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TEST"


def fake_client(tmp_path: Path, body: bytes, **kwargs: Any) -> SourceClient:
    client = SourceClient(tmp_path, "probe-fixture", retries=0, **kwargs)
    client.opener = Mock()
    client.opener.open.return_value = FakeResponse(body)
    return client


def test_raw_bytes_and_manifest_hash_are_exact(tmp_path: Path) -> None:
    body = b"observation_date,TEST\r\n2024-01-01,1.5\r\n"
    client = fake_client(tmp_path, body)
    result = client.fetch(
        "FRED", "fixture", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TEST", "text/csv"
    )
    assert result.record.raw_path is not None
    assert (tmp_path / result.record.raw_path).read_bytes() == body
    assert result.record.sha256 == hashlib.sha256(body).hexdigest()
    manifest = json.loads((tmp_path / "data/manifests/raw_manifest.jsonl").read_text())
    assert manifest["body_complete"] is True
    assert manifest["size_bytes"] == len(body)


def test_size_cap_never_claims_truncated_snapshot(tmp_path: Path) -> None:
    client = fake_client(tmp_path, b"0123456789", max_bytes=5)
    result = client.fetch(
        "FRED", "fixture", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TEST", "text/csv"
    )
    assert result.body is None
    assert result.record.body_complete is False
    assert result.record.sha256 is None
    assert result.record.error is not None and "exceeds" in result.record.error


def test_200_error_page_is_unavailable(tmp_path: Path) -> None:
    client = fake_client(tmp_path, b"<html>Not data</html>")
    result = probe_one(
        client,
        {
            "provider": "FRED",
            "id": "fixture",
            "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TEST",
            "accept": "text/csv",
            "parser": "csv",
            "dataset_candidate": "test",
            "series_candidate": "TEST",
        },
    )
    assert result["status"] == "unavailable"
    assert result["fetch"]["status"] == 200


def test_tracked_evidence_excludes_observation_values() -> None:
    original = {
        "id": "test",
        "parsed": {
            "observation_count": 1,
            "example_observation": {"period": "2024", "value": 4.2},
            "series_metadata": {"unit": "percent"},
        },
    }
    evidence = public_evidence(original)
    assert "example_observation" not in evidence["parsed"]
    assert "example_observation" in original["parsed"]


def test_probe_inventory_covers_providers_and_worldbank_modes() -> None:
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "configs/source_probes.json").read_text())
    assert {x["provider"] for x in config["probes"]} == {
        "OECD",
        "BIS",
        "IMF",
        "ECB",
        "Eurostat",
        "WorldBank",
        "FRED",
    }
    assert {x["parser"] for x in config["probes"] if x["provider"] == "WorldBank"} == {
        "wdi",
        "pink_sheet",
    }
    for probe in config["probes"] + config["terms"]:
        validate_url(probe["url"])


@pytest.mark.parametrize(
    ("parser", "body"), [("sdmx", b"<broken>"), ("pink_sheet", b"not an xlsx zip")]
)
def test_malformed_http200_is_unavailable(tmp_path: Path, parser: str, body: bytes) -> None:
    client = fake_client(tmp_path, body)
    result = probe_one(
        client,
        {
            "provider": "FRED",
            "id": "malformed",
            "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TEST",
            "accept": "text/csv",
            "parser": parser,
            "dataset_candidate": "test",
            "series_candidate": "TEST",
        },
    )
    assert result["status"] == "unavailable"
    assert result["error"]


def test_incomplete_http_body_is_recorded(tmp_path: Path) -> None:
    from http.client import IncompleteRead

    client = SourceClient(tmp_path, "probe-incomplete", retries=0)
    client.opener = Mock()
    client.opener.open.side_effect = IncompleteRead(b"partial")
    result = client.fetch(
        "FRED", "fixture", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TEST", "text/csv"
    )
    assert result.record.body_complete is False
    assert result.record.error is not None and "IncompleteRead" in result.record.error
