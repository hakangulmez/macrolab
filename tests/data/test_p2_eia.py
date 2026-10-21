"""Official EIA format guards and narrow P2 source policy selection."""

import runpy
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from macrolab.data.sources.eia import TITLE, audit, parse_frame, parse_table
from macrolab.data.sources.http import NetworkBoundaryError, validate_url

PREPARE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/p1_prepare.py"))


def frame():
    return pd.DataFrame(
        [
            ["Back to Contents", f"Data 1: {TITLE}"],
            ["Sourcekey", "RBRTE"],
            ["Date", TITLE],
            [datetime(1999, 1, 15), 11.11],
            [datetime(2020, 4, 15), 18.38],
            [datetime(2026, 9, 15), 114.16],
        ]
    )


def table():
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    rows = [
        ["Year", *months],
        ["1999", "11.11", *([""] * 11)],
        ["2020", "", "", "", "18.38", *([""] * 8)],
        ["2026", *([""] * 8), "114.16", "", "", ""],
    ]
    return (
        TITLE
        + "<table>"
        + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
        + "</table>Release Date: 10/15/2026 Next Release Date: 10/21/2026"
    ).encode()


def test_xls_observations_match_independent_html_cells_and_keep_original_cells():
    rows = parse_frame(frame())
    html_values, release = parse_table(table())
    result = audit(rows, html_values)
    assert release == "2026-10-15"
    assert result["passed"] and result["observations_compared"] == 3
    assert result["maximum_absolute_difference"] == 0
    assert rows[0]["audit"]["value_cell"] == "B4"
    assert rows[0]["audit"]["source_period"] == "1999-01-15T00:00:00"
    html_values["1999-01"] += 0.01
    with pytest.raises(ValueError, match="differs"):
        audit(rows, html_values)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "not a price"])
def test_invalid_prices_never_enter_the_candidate(value):
    content = frame().astype(object)
    content.iloc[3, 1] = value
    with pytest.raises(ValueError, match="price|positive"):
        parse_frame(content)


def test_wrong_series_duplicate_dates_and_reordered_html_months_are_rejected():
    content = frame()
    content.iloc[1, 1] = "RWTC"
    with pytest.raises(ValueError, match="source key"):
        parse_frame(content)
    content = frame()
    content.iloc[4, 0] = content.iloc[3, 0]
    with pytest.raises(ValueError, match="Duplicate"):
        parse_frame(content)
    with pytest.raises(ValueError, match="month headers"):
        parse_table(table().replace(b"<td>Jan</td>", b"<td>Apr</td>"))


def test_eia_host_permission_does_not_allow_nearby_or_non_https_hosts():
    validate_url("https://www.eia.gov/dnav/pet/hist_xls/RBRTEm.xls")
    for url in [
        "http://www.eia.gov/file",
        "https://www.eia.gov.evil.test/file",
        "https://api.eia.gov/file",
    ]:
        with pytest.raises(NetworkBoundaryError):
            validate_url(url)


def test_exact_flow_policy_rejects_an_unreviewed_version_and_cites_derived_components():
    flow = "OECD.TEST,FLOW,1.0"
    prefix = f"https://sdmx.oecd.org/public/rest/v1/data/{flow}/"
    rule = {
        "id": "oecd",
        "source": "OECD",
        "dataset": "Reviewed flow",
        "status": "allowed",
        "source_url_prefixes": [prefix],
        "attribution_by_flow": {flow: "OECD (2026), exact flow citation"},
    }
    policy = PREPARE["Policy"]({"rules": [rule]})
    row = {"source": "OECD", "source_url": prefix + "USA", "source_series_id": "USA.Q"}
    assert policy.decisions(row)[0]["status"] == "allowed"
    assert (
        policy.decisions({**row, "source_url": prefix.replace(",1.0/", ",1.1/")})[0]["status"]
        == "unclear"
    )
    assert PREPARE["citations"](rule, {"source": "Derived", "audit": {"components": [row]}}) == [
        "OECD (2026), exact flow citation"
    ]
    imf = {
        "source": "IMF",
        "attribution_by_series_prefix": {
            "IMF.RES:WEO(9.0.0).": "Source: International Monetary Fund, World Economic Outlook"
        },
    }
    assert PREPARE["citations"](
        imf, {"source": "IMF", "source_series_id": "IMF.RES:WEO(9.0.0).USA"}
    ) == ["Source: International Monetary Fund, World Economic Outlook"]


def test_p2_cannot_disable_policy_or_reuse_the_all_source_output():
    with pytest.raises(ValueError, match="P2 always"):
        PREPARE["prepare"](mode="all", candidate="p2")
