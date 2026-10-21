"""Coverage labels distinguish real sample limits from methodological notes."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any

import pytest

from macrolab.data.coverage import build_coverage

RULES = {
    "requested_sample_start": "1999-01-01",
    "staleness_months": {"M": 6, "Q": 9, "A": 24},
    "commodity_staleness_months": 3,
}


def classify(
    concept_id: str,
    *,
    start: str = "1999-01",
    end: str = "2026-09",
    scope: str = "national",
    frequency: str = "M",
    sa_flag: str = "SA",
    flags: tuple[str, ...] = (),
    gap: bool = False,
    adoption: str | None = None,
    methodology: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    first, last = (int(start[:4]) * 12 + int(start[5:]) - 1, int(end[:4]) * 12 + int(end[5:]) - 1)
    periods = [f"{month // 12:04d}-{month % 12 + 1:02d}" for month in range(first, last + 1)]
    if frequency == "A":
        periods = [str(year) for year in range(int(start[:4]), int(end[:4]) + 1)]
    if gap:
        del periods[len(periods) // 2]
    rows = [
        {
            "country": "TUR",
            "concept_id": concept_id,
            "date": period,
            "value": index + 1.0,
            "source": "Synthetic",
            "source_series_id": concept_id,
            "freq": frequency,
            "sa_flag": sa_flag,
            "methodology": methodology,
            "flags": list(flags),
        }
        for index, period in enumerate(periods)
    ]
    before = deepcopy(rows)
    countries = [{"iso3": "TUR", "name": "Synthetic country", "euro_adoption": adoption}]
    concepts = [
        {
            "concept_id": concept_id,
            "title": concept_id,
            "scope": scope,
            "default_transform": "level",
            "source_priority": ["Synthetic"],
        }
    ]
    coverage, cards = build_coverage(rows, countries, concepts, RULES, date(2026, 10, 20), [])
    assert rows == before
    assert coverage[0]["reason_code"] == coverage[0]["reason_codes"][0]
    assert coverage[0]["reason_codes"] == cards[0]["reason_codes"]
    return coverage[0], cards[0]


@pytest.mark.parametrize("concept", ["oil_brent", "commod_idx", "us_policy_rate"])
def test_current_global_factors_have_notes_without_model_limits(concept: str) -> None:
    coverage, card = classify(
        concept,
        scope="global",
        sa_flag="UNKNOWN",
        flags=("seasonal_adjustment_unknown", "global_common_factor", "covid_period"),
    )
    assert coverage["status"] == "available_note"
    assert "shared_global_factor" in coverage["reason_codes"]
    assert "seasonal_adjustment_not_model_limiting" in coverage["reason_codes"]
    assert "covid_period" in card["warnings"]


@pytest.mark.parametrize(
    ("start", "status", "reason"),
    [
        ("2005-12", "available_note", "shorter_history_through_2005"),
        ("2006-01", "limited", "history_starts_after_2005"),
    ],
)
def test_short_history_boundary_is_after_the_end_of_2005(
    start: str,
    status: str,
    reason: str,
) -> None:
    coverage, _card = classify("gdp_real", start=start)
    assert coverage["status"] == status
    assert coverage["reason_codes"] == [reason]
    assert coverage["actual_available_start"] == start + "-01"


def test_policy_sample_after_adoption_is_not_penalised_as_short_history() -> None:
    coverage, _card = classify(
        "policy_rate",
        start="2015-01",
        adoption="2015-01-01",
        sa_flag="UNKNOWN",
        flags=("shared_ecb_rate", "monthly_end_of_period"),
    )
    assert coverage["status"] == "available_note"
    assert "history_starts_after_2005" not in coverage["reason_codes"]
    assert {"shared_ecb_policy_rate", "end_of_month_policy_rate"} <= set(coverage["reason_codes"])


def test_turkish_three_month_series_keeps_its_2008_sample_limit() -> None:
    coverage, _card = classify(
        "rate_3m",
        start="2008-01",
        sa_flag="UNKNOWN",
        flags=("source_instrument_may_be_comparable_three_month_instrument",),
    )
    assert coverage["status"] == "limited"
    assert coverage["reason_code"] == "history_starts_after_2005"
    assert "comparable_three_month_instrument" in coverage["reason_codes"]


def test_turkish_three_month_history_ending_in_2008_is_still_limited() -> None:
    coverage, _card = classify(
        "rate_3m",
        start="1998-02",
        end="2008-04",
        gap=True,
        sa_flag="UNKNOWN",
        flags=("source_instrument_may_be_comparable_three_month_instrument",),
    )
    assert coverage["status"] == "limited"
    assert coverage["reason_code"] == "stale"
    assert "internal_gaps" in coverage["reason_codes"]
    assert "comparable_three_month_instrument" in coverage["reason_codes"]


@pytest.mark.parametrize("concept", ["money_broad", "oil_brent"])
def test_stale_series_are_limited_even_if_global_or_definition_notes_exist(concept: str) -> None:
    coverage, _card = classify(
        concept,
        end="2023-12",
        scope="global" if concept == "oil_brent" else "national",
        flags=("national_broad_money_definition",),
    )
    assert coverage["status"] == "limited"
    assert coverage["reason_code"] == "stale"


@pytest.mark.parametrize("concept", ["ind_prod", "cpi", "ppi", "employment"])
def test_unknown_adjustment_limits_seasonal_model_inputs(concept: str) -> None:
    coverage, _card = classify(concept, sa_flag="UNKNOWN")
    assert coverage["status"] == "limited"
    assert coverage["reason_code"] == "seasonal_adjustment_unknown"


@pytest.mark.parametrize("concept", ["cpi", "cpi_core"])
@pytest.mark.parametrize(
    ("methodology", "flags", "expected"),
    [
        ("HICP", (), "hicp_methodology"),
        ("N", (), "national_cpi_methodology"),
        (None, ("HICP",), "hicp_methodology"),
    ],
)
def test_cpi_methodology_is_an_explicit_note_from_source_metadata(
    concept: str,
    methodology: str | None,
    flags: tuple[str, ...],
    expected: str,
) -> None:
    coverage, _card = classify(concept, methodology=methodology, flags=flags)
    assert coverage["status"] == "available_note"
    assert coverage["reason_codes"] == [expected]


def test_price_methodology_notes_do_not_hide_short_history_limits() -> None:
    coverage, _card = classify("cpi", start="2008-01", methodology="HICP")
    assert coverage["status"] == "limited"
    assert coverage["reason_code"] == "history_starts_after_2005"
    assert "hicp_methodology" in coverage["reason_codes"]


@pytest.mark.parametrize(
    ("concept", "flags", "expected"),
    [
        (
            "ppi",
            ("manufacturing_domestic_market", "PPI_market_scope_explicit"),
            "domestic_manufacturing_ppi",
        ),
        ("cpi", ("classification_COICOP2018",), "coicop2018_classification"),
        ("cpi", ("ECOICOP2",), "ecoicop2_classification"),
        ("cli", ("OECD_harmonised_index",), "oecd_harmonised_index"),
    ],
)
def test_new_source_definitions_receive_specific_reason_codes(
    concept: str,
    flags: tuple[str, ...],
    expected: str,
) -> None:
    coverage, card = classify(concept, flags=flags)
    assert coverage["status"] == "available_note"
    assert coverage["reason_codes"] == [expected]
    assert set(card["warnings"]) == set(flags)


@pytest.mark.parametrize("concept", ["gov_debt", "gov_balance"])
def test_annual_fiscal_series_remain_native_frequency_notes(concept: str) -> None:
    coverage, _card = classify(concept, frequency="A", end="2025-12", sa_flag="UNKNOWN")
    assert coverage["status"] == "available_note"
    assert "annual_native_frequency" in coverage["reason_codes"]


def test_internal_gaps_limit_coverage_but_special_period_flags_do_not() -> None:
    flags = ("covid_period", "elb_period", "large_observation_change", "plausibility_outlier")
    complete, card = classify("unemp", flags=flags)
    gapped, _card = classify("unemp", flags=flags, gap=True)
    assert complete["status"] == "available"
    assert complete["reason_codes"] == ["coverage_complete"]
    assert set(card["warnings"]) == set(flags)
    assert gapped["status"] == "limited"
    assert gapped["reason_code"] == "internal_gaps"
    assert gapped["missing_periods"] == 1


def test_missing_cell_preserves_source_specific_explanation() -> None:
    country = {"iso3": "CHL", "name": "Chile"}
    concept = {
        "concept_id": "cli",
        "title": "CLI",
        "scope": "national",
        "default_transform": "level",
        "source_priority": ["OECD"],
    }
    issue = {"country": "CHL", "concept_id": "cli", "reason_code": "source_not_published"}
    coverage, cards = build_coverage([], [country], [concept], RULES, date(2026, 10, 20), [issue])
    assert coverage[0]["status"] == "missing"
    assert coverage[0]["reason_code"] == "source_not_published"
    assert cards[0]["issues"] == [issue]


def test_serialised_parquet_flags_cannot_silently_change_classification() -> None:
    row = {
        "country": "USA",
        "concept_id": "policy_rate",
        "date": "2026-09",
        "flags": '["monthly_end_of_period"]',
    }
    country = {"iso3": "USA", "name": "United States"}
    concept = {"concept_id": "policy_rate"}
    with pytest.raises(ValueError, match="decoded lists"):
        build_coverage([row], [country], [concept], RULES, date(2026, 10, 20), [])
