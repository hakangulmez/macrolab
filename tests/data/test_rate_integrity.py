"""Rate metadata and monetary-union boundaries must survive harmonisation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from macrolab.data.harmonise import derive_term_spread, splice_policy_rates


def rate(
    concept: str,
    value: float,
    *,
    country: str = "USA",
    period: str = "2024-01",
    unit: str = "PA",
) -> dict[str, Any]:
    return {
        "country": country,
        "concept_id": concept,
        "source": "OECD",
        "source_series_id": f"synthetic/{country}/{concept}",
        "date": period,
        "value": value,
        "unit": unit,
        "unit_label": "Percent per annum" if unit == "PA" else unit,
        "unit_mult": 0,
        "sa_flag": "NA",
        "price_basis": "not_applicable",
        "base_year": None,
        "freq": "M",
        "obs_status": "reported",
        "source_url": "https://sdmx.oecd.org/synthetic-rate-fixture",
        "attribution": "Synthetic fixture; OECD rate unit vocabulary",
        "flags": [],
    }


def test_oecd_pa_rates_produce_percentage_point_spread_and_retain_components() -> None:
    long, short = rate("rate_10y", 4.0), rate("rate_3m", 5.5)
    before = deepcopy([long, short])

    spread = derive_term_spread([long, short])

    assert len(spread) == 1
    assert spread[0]["value"] == pytest.approx(-1.5)
    assert spread[0]["unit"] == "percentage points"
    assert spread[0]["unit_mult"] == 0
    assert spread[0]["source"] == "Derived"
    assert spread[0]["audit"]["components"] == before
    assert [long, short] == before


@pytest.mark.parametrize("invalid_unit", ["IX", "USD", "Percent of GDP", "Percent change"])
@pytest.mark.parametrize("invalid_concept", ["rate_10y", "rate_3m"])
def test_spread_rejects_incompatible_units_even_when_values_are_numeric(
    invalid_unit: str, invalid_concept: str
) -> None:
    rows = [rate("rate_10y", 4.0), rate("rate_3m", 5.5)]
    for row in rows:
        if row["concept_id"] == invalid_concept:
            row["unit"] = invalid_unit
            row["unit_label"] = invalid_unit

    assert derive_term_spread(rows) == []


def test_euro_splice_marks_only_adoption_boundary_and_preserves_source_identity() -> None:
    countries = [{"iso3": "GRC", "euro_adoption": "2001-01-01"}, {"iso3": "EA"}]
    rows = [
        rate("policy_rate", 7.0, country="GRC", period="2000-12"),
        rate("policy_rate", 8.0, country="GRC", period="2001-01"),
        rate("policy_rate", 9.0, country="GRC", period="2001-02"),
        rate("policy_rate", 4.0, country="EA", period="2001-01"),
        rate("policy_rate", 4.5, country="EA", period="2001-02"),
    ]
    for row in rows:
        row["source"] = "BIS"
        row["source_series_id"] = f"WS_CBPOL/M.{row['country']}"
    before = deepcopy(rows)

    spliced, issues = splice_policy_rates(rows, countries)
    national = {row["date"]: row for row in spliced if row["country"] == "GRC"}

    assert not issues
    assert {period: row["value"] for period, row in national.items()} == {
        "2000-12": 7.0,
        "2001-01": 4.0,
        "2001-02": 4.5,
    }
    assert not national["2000-12"].get("shared", False)
    assert "euro_adoption_break" in national["2001-01"]["flags"]
    assert "euro_adoption_break" not in national["2001-02"]["flags"]
    for period in ("2001-01", "2001-02"):
        assert national[period]["shared"] is True
        assert national[period]["source_country"] == "EA"
        assert national[period]["source"] == "BIS"
        assert national[period]["source_series_id"] == "WS_CBPOL/M.EA"
        assert "shared_ecb_rate" in national[period]["flags"]
    assert rows == before


def test_missing_shared_rate_leaves_post_adoption_gap_instead_of_national_substitute() -> None:
    rows = [
        rate("policy_rate", 7.0, country="GRC", period="2000-12"),
        rate("policy_rate", 8.0, country="GRC", period="2001-01"),
    ]

    spliced, issues = splice_policy_rates(
        rows, [{"iso3": "GRC", "euro_adoption": "2001-01-01"}, {"iso3": "EA"}]
    )

    assert [(row["date"], row["value"]) for row in spliced] == [("2000-12", 7.0)]
    assert any(
        issue["code"] == "shared_rate_missing"
        and issue["country"] == "GRC"
        and issue["concept_id"] == "policy_rate"
        for issue in issues
    )
