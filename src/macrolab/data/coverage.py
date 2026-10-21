"""Coverage states and source-attributed series cards, including missing cells."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from macrolab.data.standardise import period_ordinal, period_start

# Shorter history through 2005-12-31 is informational. A later beginning is a
# modelling limit only when it also falls after the requested/adoption sample.
SHORT_HISTORY_NOTE_BOUNDARY = "2005-12-31"
LIMITING_REASON_CODES = (
    "no_observations_in_requested_sample",
    "stale",
    "internal_gaps",
    "history_starts_after_2005",
    "seasonal_adjustment_unknown",
)
SEASONALLY_RELEVANT_CONCEPTS = {
    "gdp_real",
    "cons_priv",
    "cons_gov",
    "gfcf",
    "exports_real",
    "imports_real",
    "ind_prod",
    "retail_vol",
    "cli",
    "cpi",
    "cpi_core",
    "ppi",
    "gdp_defl",
    "house_real",
    "ulc",
    "unemp",
    "employment",
    "lfpr",
    "ca_gdp",
    "gov_balance",
}
NOTE_FLAGS = {
    "native_frequency_differs_from_catalogue": "native_frequency_differs_from_catalogue",
    "adjustment_changes_within_series": "adjustment_changes_within_series",
    "aggregate_definition_warning": "aggregate_definition",
    "unit_multiplier_not_reported": "unit_multiplier_not_reported",
    "cross_country_adjustment_mismatch": "cross_country_adjustment_mismatch",
    "source_instrument_may_be_comparable_three_month_instrument": (
        "comparable_three_month_instrument"
    ),
    "shared_ecb_rate": "shared_ecb_policy_rate",
    "euro_adoption_break": "euro_adoption_break",
    "not_seasonally_adjusted": "not_seasonally_adjusted",
    "age_15_64": "working_age_15_64",
    "national_broad_money_definition": "national_broad_money_definition",
    "national_fiscal_definitions_may_differ": "national_fiscal_definition",
    "HICP": "hicp_methodology",
    "classification_COICOP2018": "coicop2018_classification",
    "ECOICOP2": "ecoicop2_classification",
    "excludes_energy_food_alcohol_tobacco": "core_price_exclusion_definition",
    "manufacturing_domestic_market": "domestic_manufacturing_ppi",
    "OECD_harmonised_index": "oecd_harmonised_index",
    "confidence_percentage_balance_not_normalised_index": "confidence_percentage_balance",
    "source_currency_history_as_published": "source_currency_history_as_published",
    "amplitude_adjusted": "amplitude_adjusted_index",
    "market_value": "market_value_measure",
    "adjusted_for_breaks": "adjusted_for_breaks",
    "maastricht_consolidated_gross_debt": "maastricht_debt_definition",
}


def _classification(
    concept: dict[str, Any],
    values: list[dict[str, Any]],
    flags: set[str],
    start: str,
) -> tuple[str, list[str]]:
    """Separate model-relevant limits from explicit definition notes, not all warnings."""
    limits = set(LIMITING_REASON_CODES[:3]) & flags
    notes = {reason for flag, reason in NOTE_FLAGS.items() if flag in flags}
    frequency = values[0]["freq"]
    concept_id = concept["concept_id"]
    if concept_id in {"cpi", "cpi_core"}:
        methodologies = {row.get("methodology") for row in values}
        if "HICP" in methodologies:
            notes.add("hicp_methodology")
        if "N" in methodologies:
            notes.add("national_cpi_methodology")
    if "shorter_history" in flags:
        if start > SHORT_HISTORY_NOTE_BOUNDARY:
            limits.add("history_starts_after_2005")
        else:
            notes.add("shorter_history_through_2005")
    unknown_sa = any(row["sa_flag"] == "UNKNOWN" for row in values) or bool(
        flags & {"seasonal_adjustment_unknown", "seasonal_adjustment_not_reported"}
    )
    if unknown_sa:
        if (
            concept["scope"] != "global"
            and frequency != "A"
            and concept_id in SEASONALLY_RELEVANT_CONCEPTS
        ):
            limits.add("seasonal_adjustment_unknown")
        else:
            notes.add("seasonal_adjustment_not_model_limiting")
    if concept["scope"] == "global":
        notes.add("shared_global_factor")
    if concept_id in {"policy_rate", "us_policy_rate"} and "monthly_end_of_period" in flags:
        notes.add("end_of_month_policy_rate")
    if frequency == "A":
        notes.add("annual_native_frequency")
    reasons = [reason for reason in LIMITING_REASON_CODES if reason in limits] + sorted(notes)
    return (
        "limited" if limits else "available_note" if notes else "available",
        reasons or ["coverage_complete"],
    )


def build_coverage(
    rows: list[dict[str, Any]],
    countries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    rules: dict[str, Any],
    as_of: date,
    issues: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["country"], row["concept_id"])].append(row)
    coverage, cards = [], []
    for country in countries:
        for concept in concepts:
            key = (country["iso3"], concept["concept_id"])
            values = sorted(groups.get(key, []), key=lambda row: row["date"])
            flags: set[str] = set()
            sample_start = str(rules["requested_sample_start"])
            if concept["concept_id"] == "policy_rate" and country.get("euro_adoption"):
                sample_start = max(sample_start, country["euro_adoption"])
            result: dict[str, Any] = {
                "country": key[0],
                "concept_id": key[1],
                "status": "missing",
                "first_date": None,
                "last_date": None,
                "observations": 0,
                "frequency": None,
                "sources": [],
                "flags": [],
                "missing_periods": None,
                "requested_sample_start": sample_start,
                "actual_available_start": None,
                "stale": False,
            }
            sources: dict[tuple[str, str], dict[str, Any]] = {}
            relevant = [
                issue
                for issue in issues
                if issue.get("concept_id") == key[1]
                and issue.get("country") in (None, "ALL", key[0], "GLOBAL")
            ]
            if values:
                for row in values:
                    if not isinstance(row["flags"], list) or any(
                        not isinstance(flag, str) for flag in row["flags"]
                    ):
                        raise ValueError("Coverage requires decoded lists of observation flags")
                    flags.update(row["flags"])
                    source_key = (row["source"], row["source_series_id"])
                    if source_key not in sources:
                        sources[source_key] = {
                            field: row.get(field)
                            for field in (
                                "source",
                                "source_series_id",
                                "source_url",
                                "attribution",
                                "terms_status",
                                "unit",
                                "unit_mult",
                                "sa_flag",
                                "price_basis",
                                "base_year",
                                "freq",
                                "shared",
                                "source_geo",
                                "variant",
                                "source_unit",
                                "unit_label",
                                "definition",
                                "source_adjustment",
                                "source_price_base",
                                "source_country",
                                "aggregation",
                            )
                        }
                        sources[source_key]["first_date"] = row["date"]
                    sources[source_key]["last_date"] = row["date"]
                freq = values[0]["freq"]
                if len({row["freq"] for row in values}) != 1:
                    raise ValueError(f"Mixed native frequencies in selected series {key}")
                first, last = values[0]["date"], values[-1]["date"]
                start = period_start(first, freq)
                final_date = date.fromisoformat(period_start(last, freq))
                age_months = (as_of.year - final_date.year) * 12 + as_of.month - final_date.month
                # A quarterly/annual observation represents its whole period, not just its start.
                age_months -= 2 if freq == "Q" else 11 if freq == "A" else 0
                threshold = (
                    rules["commodity_staleness_months"]
                    if key[1] in {"oil_brent", "commod_idx"}
                    else rules["staleness_months"][freq]
                )
                stale = age_months > threshold or any("stale" in flag for flag in flags)
                gaps = period_ordinal(last, freq) - period_ordinal(first, freq) + 1 - len(values)
                if start > sample_start:
                    flags.add("shorter_history")
                if gaps:
                    flags.add("internal_gaps")
                if stale:
                    flags.add("stale")
                if len({row["sa_flag"] for row in values}) > 1:
                    flags.add("adjustment_changes_within_series")
                if any("composition" in flag or "aggregate" in flag for flag in flags):
                    flags.add("aggregate_definition_warning")
                actual_start = next(
                    (
                        period_start(row["date"], freq)
                        for row in values
                        if period_start(row["date"], freq) >= sample_start
                    ),
                    None,
                )
                if actual_start is None:
                    flags.add("no_observations_in_requested_sample")
                status, reasons = _classification(concept, values, flags, start)
                result.update(
                    {
                        "status": status,
                        "first_date": first,
                        "last_date": last,
                        "observations": len(values),
                        "frequency": freq,
                        "sources": sorted({row["source"] for row in values}),
                        "missing_periods": gaps,
                        "stale": stale,
                        "actual_available_start": actual_start,
                    }
                )
            else:
                flags.add("no_verified_mapping_or_observations")
                reasons = sorted(
                    {issue["reason_code"] for issue in relevant if issue.get("reason_code")}
                ) or ["no_verified_mapping_or_observations"]
            result["flags"] = sorted(flags)
            result["reason_codes"] = reasons
            result["reason_code"] = reasons[0]
            cards.append(
                {
                    **result,
                    "title": concept["title"],
                    "scope": concept["scope"],
                    "country_name": country["name"],
                    "source_segments": list(sources.values()),
                    "definition": concept.get("definition", concept["title"]),
                    "default_transform": concept["default_transform"],
                    "aggregation_rules": concept.get("aggregation_rules"),
                    "source_priority": concept["source_priority"],
                    "warnings": sorted(flags),
                    "issues": relevant,
                    "policy_label": "ECB rate (shared)"
                    if key[1] == "policy_rate" and country.get("monetary_union") == "EA"
                    else None,
                    "euro_adoption": country.get("euro_adoption")
                    if key[1] == "policy_rate"
                    else None,
                    "notes_status": "DRAFT",
                    "publication_approved": False,
                }
            )
            coverage.append(result)
    return coverage, cards
