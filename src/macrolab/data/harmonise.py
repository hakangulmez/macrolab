"""Source selection, shared-rate history and explicit derived series."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from macrolab.data.standardise import period_start


def source_priority(definition: dict[str, Any]) -> list[str]:
    result = []
    for source in definition["source_priority"]:
        label = (
            "WorldBank"
            if str(source).startswith("World Bank")
            else str(source).split(" ")[0].split("/")[0]
        )
        if label.lower() in {"national", "national/ECB"}:
            label = "ECB"
        result.append(label)
    return result


def harmonise(
    rows: list[dict[str, Any]],
    countries: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    rules: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    definitions = {concept["concept_id"]: concept for concept in concepts}
    country_info = {country["iso3"]: country for country in countries}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    issues: list[dict[str, Any]] = []
    for row in rows:
        if row["concept_id"] not in definitions:
            continue
        if row["country"] == "GLOBAL":
            for iso3 in country_info:
                expanded = {**row, "country": iso3, "shared": True, "source_country": "GLOBAL"}
                groups[(iso3, row["concept_id"])].append(expanded)
        elif row["country"] in country_info:
            groups[(row["country"], row["concept_id"])].append(row)
    selected: list[dict[str, Any]] = []
    losing: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    for (country, concept), candidates in sorted(groups.items()):
        definition = definitions[concept]
        priorities = source_priority(definition)
        by_series: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in candidates:
            by_series[(row["source"], row["source_series_id"], row["freq"])].append(row)
        choices = []
        for key, values in by_series.items():
            dates: dict[str, dict[str, Any]] = {}
            conflict = False
            for value in values:
                old = dates.get(value["date"])
                if old and abs(old["value"] - value["value"]) > 1e-10:
                    conflict = True
                dates[value["date"]] = value
            if conflict:
                issues.append(
                    {
                        "code": "conflicting_duplicate",
                        "country": country,
                        "concept_id": concept,
                        "source": key[0],
                        "series": key[1],
                    }
                )
                continue
            values = sorted(dates.values(), key=lambda value: value["date"])
            identity = values[0]
            hicp = (
                "HICP"
                in (
                    str(identity.get("unit", ""))
                    + " "
                    + key[1]
                    + " "
                    + str(identity.get("measure", ""))
                    + " "
                    + str(identity.get("flags", []))
                ).upper()
            )
            eu = country_info[country].get("eu_member") is True or country == "EA"
            required_hicp = concept in {"cpi", "cpi_core"} and eu
            if required_hicp and not hicp:
                continue
            frequency_mismatch = key[2] != definition["native_frequency"]
            rank = priorities.index(key[0]) if key[0] in priorities else len(priorities)
            adequate = len(values) >= rules["adequate_history"][key[2]]
            stale = False
            if rules.get("as_of_date"):
                as_of = date.fromisoformat(rules["as_of_date"])
                latest = date.fromisoformat(period_start(values[-1]["date"], key[2]))
                age = (as_of.year - latest.year) * 12 + as_of.month - latest.month
                age -= 2 if key[2] == "Q" else 11 if key[2] == "A" else 0
                stale = age > rules["staleness_months"][key[2]]
            candidate_priority = int(identity.get("candidate_priority", 0))
            # Prefer the declared provider when history is adequate. If no provider
            # has adequate history, keep the longest eligible series and disclose it.
            ordering = (
                (stale, False, rank, candidate_priority, frequency_mismatch, -len(values), key)
                if adequate
                else (stale, True, -len(values), rank, candidate_priority, frequency_mismatch, key)
            )
            choices.append((ordering, values))
        if not choices:
            losing.extend(
                {**row, "selection_status": "rejected_definition_or_duplicate"}
                for row in candidates
            )
            issues.append(
                {
                    "code": "no_eligible_series",
                    "country": country,
                    "concept_id": concept,
                    "detail": "No unambiguous series meets required definition",
                }
            )
            continue
        choices.sort(key=lambda item: item[0])
        chosen = choices[0][1]
        winner = (chosen[0]["source"], chosen[0]["source_series_id"], chosen[0]["freq"])
        flags = []
        if winner[2] != definition["native_frequency"]:
            flags.append("native_frequency_differs_from_catalogue")
        selected.extend({**row, "flags": sorted(set(row["flags"] + flags))} for row in chosen)
        losing.extend(
            {**row, "selection_status": "lower_priority_or_shorter_history"}
            for row in candidates
            if (row["source"], row["source_series_id"], row["freq"]) != winner
        )
        prior_sources = (
            priorities[: priorities.index(winner[0])] if winner[0] in priorities else priorities
        )
        source_counts = {
            source: sum(row["source"] == source for row in candidates) for source in priorities
        }
        selections.append(
            {
                "country": country,
                "concept_id": concept,
                "selected_source": winner[0],
                "source_series_id": winner[1],
                "frequency": winner[2],
                "source_priority": priorities,
                "fallback": bool(prior_sources),
                "prior_sources": prior_sources,
                "candidate_observations_by_source": source_counts,
                "selected_is_stale": choices[0][0][0],
                "reason": (
                    "prefer current histories; then first eligible source with adequate history; "
                    "otherwise longest available; stale observations retained with warnings "
                    "only where no current eligible candidate exists"
                ),
            }
        )
    return selected, losing, selections, issues


def splice_policy_rates(
    rows: list[dict[str, Any]],
    countries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shared = [row for row in rows if row["country"] == "EA" and row["concept_id"] == "policy_rate"]
    result = list(rows)
    issues = []
    for country in countries:
        iso3, adoption = country["iso3"], country.get("euro_adoption")
        if iso3 == "EA" or not adoption:
            continue
        result = [
            row
            for row in result
            if not (
                row["country"] == iso3
                and row["concept_id"] == "policy_rate"
                and period_start(row["date"], row["freq"]) >= adoption
            )
        ]
        if not shared:
            issues.append(
                {
                    "code": "shared_rate_missing",
                    "country": iso3,
                    "concept_id": "policy_rate",
                    "detail": "No euro-area policy source",
                }
            )
            continue
        for row in shared:
            if period_start(row["date"], row["freq"]) >= adoption:
                result.append(
                    {
                        **row,
                        "country": iso3,
                        "source_country": "EA",
                        "shared": True,
                        "policy_label": "ECB rate (shared)",
                        "euro_adoption": adoption,
                        "flags": sorted(
                            set(
                                row["flags"]
                                + ["shared_ecb_rate"]
                                + (
                                    ["euro_adoption_break"]
                                    if period_start(row["date"], row["freq"]) == adoption
                                    else []
                                )
                            )
                        ),
                    }
                )
    return result, issues


def derive_term_spread(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    long_rates = {
        (r["country"], r["date"], r["freq"]): r for r in rows if r["concept_id"] == "rate_10y"
    }
    result = []
    for short in rows:
        if short["concept_id"] != "rate_3m":
            continue
        long = long_rates.get((short["country"], short["date"], short["freq"]))
        if long is None or long["unit_mult"] != short["unit_mult"]:
            continue
        if not all(
            str(r["unit"]).strip().lower() in {"pa", "percent", "%", "p.a.", "percent per annum"}
            for r in (long, short)
        ):
            continue
        result.append(
            {
                **long,
                "concept_id": "term_spread",
                "source": "Derived",
                "source_series_id": f"{long['source_series_id']} minus {short['source_series_id']}",
                "value": long["value"] - short["value"],
                "unit": "percentage points",
                "sa_flag": "NA",
                "price_basis": "not_applicable",
                "base_year": None,
                "source_url": long["source_url"],
                "component_urls": [long["source_url"], short["source_url"]],
                "attribution": (
                    f"MacroLab: 10-year minus 3-month. "
                    f"{long['attribution']}; {short['attribution']}"
                ),
                "audit": {"parser": "derived_term_spread", "components": [long, short]},
                "flags": sorted(set(long["flags"] + short["flags"] + ["derived"])),
            }
        )
    return result
