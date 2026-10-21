"""Current series take precedence without splicing or concealing source choices."""

from __future__ import annotations

from typing import Any

from macrolab.data.harmonise import harmonise

COUNTRIES = [{"iso3": "DEU", "name": "Germany", "eu_member": True}]
CONCEPTS = [
    {
        "concept_id": "ind_prod",
        "title": "Industrial production",
        "scope": "national",
        "native_frequency": "M",
        "default_transform": "yoy",
        "source_priority": ["OECD", "Eurostat"],
    }
]
RULES = {
    "as_of_date": "2026-10-20",
    "adequate_history": {"M": 120, "Q": 40, "A": 10},
    "staleness_months": {"M": 6, "Q": 9, "A": 24},
}


def history(
    source: str,
    latest: str,
    *,
    adjustment: str = "SA",
    omit: str | None = None,
) -> list[dict[str, Any]]:
    final_year, final_month = map(int, latest.split("-"))
    rows = []
    for ordinal in range(2015 * 12, final_year * 12 + final_month):
        year, month = divmod(ordinal, 12)
        period = f"{year}-{month + 1:02d}"
        if period == omit:
            continue
        rows.append(
            {
                "country": "DEU",
                "concept_id": "ind_prod",
                "source": source,
                "source_series_id": f"synthetic/{source}/DEU/{adjustment}",
                "date": period,
                "value": float(ordinal % 12 + (100 if source == "OECD" else 200)),
                "freq": "M",
                "unit": "IX",
                "unit_mult": 0,
                "sa_flag": adjustment,
                "candidate_priority": 0 if adjustment == "SA" else 2,
                "flags": [] if adjustment == "SA" else ["not_seasonally_adjusted"],
            }
        )
    return rows


def test_current_eurostat_replaces_stale_oecd_without_filling_fallback_gaps() -> None:
    oecd = history("OECD", "2025-12")
    eurostat = history("Eurostat", "2026-09", omit="2024-06")

    selected, losing, ledger, issues = harmonise(oecd + eurostat, COUNTRIES, CONCEPTS, RULES)

    assert selected == eurostat
    assert "2024-06" not in {row["date"] for row in selected}
    assert any(row["date"] == "2024-06" for row in losing)
    assert len(losing) == len(oecd)
    assert {row["source"] for row in losing} == {"OECD"}
    assert ledger[0]["selected_source"] == "Eurostat"
    assert ledger[0]["selected_is_stale"] is False
    assert ledger[0]["fallback"] is True
    assert not issues


def test_current_nsa_replaces_stale_sa_within_same_provider_and_retains_warning() -> None:
    stale_sa = history("OECD", "2025-12")
    current_nsa = history("OECD", "2026-09", adjustment="NSA", omit="2024-06")

    selected, losing, ledger, issues = harmonise(stale_sa + current_nsa, COUNTRIES, CONCEPTS, RULES)

    assert selected == current_nsa
    assert {row["sa_flag"] for row in selected} == {"NSA"}
    assert all("not_seasonally_adjusted" in row["flags"] for row in selected)
    assert "2024-06" not in {row["date"] for row in selected}
    assert len(losing) == len(stale_sa)
    assert ledger[0]["selected_is_stale"] is False
    assert ledger[0]["fallback"] is False
    assert not issues


def test_provider_priority_is_retained_among_current_adequate_histories() -> None:
    # Six months old is current under the configured strict greater-than threshold.
    oecd = history("OECD", "2026-04", omit="2024-06")
    eurostat = history("Eurostat", "2026-09")

    selected, losing, ledger, issues = harmonise(oecd + eurostat, COUNTRIES, CONCEPTS, RULES)

    assert selected == oecd
    assert "2024-06" not in {row["date"] for row in selected}
    assert len(losing) == len(eurostat)
    assert ledger[0]["selected_source"] == "OECD"
    assert ledger[0]["selected_is_stale"] is False
    assert ledger[0]["fallback"] is False
    assert not issues


def test_all_stale_histories_remain_available_with_explicit_staleness_in_ledger() -> None:
    oecd = history("OECD", "2025-06")
    eurostat = history("Eurostat", "2025-12")

    selected, _losing, ledger, issues = harmonise(oecd + eurostat, COUNTRIES, CONCEPTS, RULES)

    assert selected == oecd
    assert ledger[0]["selected_source"] == "OECD"
    assert ledger[0]["selected_is_stale"] is True
    assert not issues
