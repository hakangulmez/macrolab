"""Eurostat HICP ECOICOP2 and national-account/labour/fiscal fallbacks."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from macrolab.data.sources.bis import fetch_issue, finite
from macrolab.data.sources.http import FetchResult, SourceClient

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def jsonstat_observations(payload: dict[str, Any]) -> list[tuple[int, dict[str, str], float, str]]:
    dimensions: list[str] = payload.get("id", [])
    sizes: list[int] = payload.get("size", [])
    if not dimensions or len(dimensions) != len(sizes) or any(size == 0 for size in sizes):
        return []
    indexes: list[dict[int, str]] = []
    for dimension in dimensions:
        index = payload["dimension"][dimension]["category"]["index"]
        indexes.append(
            {int(value): key for key, value in index.items()}
            if isinstance(index, dict)
            else dict(enumerate(index))
        )
    values = payload.get("value", {})
    status = payload.get("status", {})
    iterator = values.items() if isinstance(values, dict) else enumerate(values)
    result = []
    for flat, value in iterator:
        if not finite(value):
            continue
        flat_index = int(flat)
        remaining = flat_index
        coordinates = [0] * len(sizes)
        for axis in reversed(range(len(sizes))):
            coordinates[axis] = remaining % sizes[axis]
            remaining //= sizes[axis]
        if remaining:
            raise ValueError("JSON-stat flat index exceeds declared dimensions")
        selectors = {
            dimension: indexes[axis][coordinates[axis]] for axis, dimension in enumerate(dimensions)
        }
        obs_status = (
            status.get(str(flat), "")
            if isinstance(status, dict)
            else (status[flat_index] if flat_index < len(status) else "")
        )
        result.append((flat_index, selectors, float(value), str(obs_status or "not_reported")))
    return result


def normalise_eurostat(
    payload: dict[str, Any],
    fetched: FetchResult,
    countries: list[dict[str, Any]],
    specification: dict[str, Any],
) -> list[dict[str, Any]]:
    country_map = {str(c["iso2"]): str(c["iso3"]) for c in countries if c.get("iso2")}
    if "GR" in country_map:
        country_map["EL"] = country_map.pop("GR")
    if "GB" in country_map:
        country_map["UK"] = country_map.pop("GB")
    available = payload.get("dimension", {}).get("geo", {}).get("category", {}).get("index", {})
    aggregate = next((code for code in ("EA21", "EA20", "EA19", "EA") if code in available), None)
    if aggregate and any(c["iso3"] == "EA" for c in countries):
        country_map[aggregate] = "EA"
    rows: list[dict[str, Any]] = []
    for flat_index, selectors, value, status in jsonstat_observations(payload):
        geo = selectors.get("geo", "")
        if geo not in country_map:
            continue
        country = country_map[geo]
        flags = list(specification.get("flags", []))
        if country == "EA":
            flags.append("euro_area_fixed_composition_" + geo)
            if geo != "EA21":
                flags.append("euro_area_composition_mismatch")
        series_selector = {key: val for key, val in selectors.items() if key != "time"}
        rows.append(
            {
                "country": country,
                "concept_id": specification["concept"],
                "source": "Eurostat",
                "source_series_id": specification["dataset"]
                + "."
                + ".".join(series_selector.values()),
                "date": selectors["time"],
                "value": value,
                "unit": specification["unit"],
                "unit_mult": specification.get("unit_mult", 0),
                "sa_flag": specification["sa_flag"],
                "price_basis": specification["price_basis"],
                "base_year": specification.get("base_year"),
                "freq": selectors["freq"],
                "obs_status": status,
                "source_geo": geo,
                "source_url": fetched.record.url,
                "raw_path": fetched.record.raw_path,
                "attribution": (
                    f"Eurostat, {specification['dataset']}; accessed {fetched.record.retrieved_utc}"
                ),
                "terms_status": "conditional",
                "flags": flags,
                "audit": {
                    "parser": "jsonstat",
                    "source_period": selectors["time"],
                    "selector": series_selector,
                    "flat_index": flat_index,
                },
                "source_metadata": {
                    "dataset_label": payload.get("label"),
                    "updated": payload.get("updated"),
                    "dimension_labels": {
                        key: payload["dimension"][key]["category"].get("label", {}).get(val, val)
                        for key, val in series_selector.items()
                    },
                },
            }
        )
    return rows


def specifications() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "concept": "cpi",
            "dataset": "prc_hicp_minr",
            "filters": {"unit": "I25", "coicop18": "TOTAL"},
            "unit": "index",
            "sa_flag": "NSA",
            "price_basis": "consumer_prices",
            "base_year": "2025",
            "flags": ["HICP", "ECOICOP2"],
        },
        {
            "concept": "cpi_core",
            "dataset": "prc_hicp_minr",
            "filters": {"unit": "I25", "coicop18": "TOT_X_NRG_FOOD"},
            "unit": "index",
            "sa_flag": "NSA",
            "price_basis": "consumer_prices",
            "base_year": "2025",
            "flags": ["HICP", "ECOICOP2", "excludes_energy_food_alcohol_tobacco"],
        },
        {
            "concept": "gov_debt",
            "dataset": "gov_10dd_edpt1",
            "filters": {"unit": "PC_GDP", "sector": "S13", "na_item": "GD"},
            "unit": "percent_gdp",
            "sa_flag": "UNKNOWN",
            "price_basis": "nominal",
            "flags": ["seasonal_adjustment_unknown", "maastricht_consolidated_gross_debt"],
        },
        {
            "concept": "gov_balance",
            "dataset": "gov_10dd_edpt1",
            "filters": {"unit": "PC_GDP", "sector": "S13", "na_item": "B9"},
            "unit": "percent_gdp",
            "sa_flag": "UNKNOWN",
            "price_basis": "nominal",
            "flags": ["seasonal_adjustment_unknown"],
        },
        {
            "concept": "unemp",
            "dataset": "une_rt_m",
            "filters": {"unit": "PC_ACT", "s_adj": "SA", "sex": "T", "age": "TOTAL"},
            "unit": "percent",
            "sa_flag": "SA",
            "price_basis": "not_applicable",
            "flags": ["harmonised_unemployment"],
        },
    ]
    for concept, item in {
        "gdp_real": "B1GQ",
        "cons_priv": "P31_S14_S15",
        "gfcf": "P51G",
        "cons_gov": "P3_S13",
        "exports_real": "P6",
        "imports_real": "P7",
    }.items():
        items.append(
            {
                "concept": concept,
                "dataset": "namq_10_gdp",
                "filters": {"unit": "CLV10_MEUR", "s_adj": "SCA", "na_item": item},
                "unit": "EUR",
                "unit_mult": 6,
                "sa_flag": "SA",
                "price_basis": "chain_linked_volume",
                "base_year": "2010",
                "flags": ["calendar_adjusted", "chain_linked_volumes_nonadditive"],
            }
        )
    return items


def fetch_eurostat(client: SourceClient, countries: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for specification in specifications():
        request_id = "eurostat_" + specification["concept"]
        query = urlencode({"lang": "EN", **specification["filters"]})
        url = f"{API}/{specification['dataset']}?{query}"
        fetched = client.fetch("Eurostat", request_id, url, "application/json")
        if fetched.record.status != 200 or fetched.body is None:
            issues.append(fetch_issue("Eurostat", request_id, fetched))
            continue
        payload = json.loads(fetched.body)
        parsed = normalise_eurostat(payload, fetched, countries, specification)
        rows.extend(parsed)
        seen = {row["country"] for row in parsed}
        for country in countries:
            if country["iso3"] not in seen:
                issues.append(
                    {
                        "source": "Eurostat",
                        "code": "series_not_returned",
                        "country": country["iso3"],
                        "concept_id": specification["concept"],
                        "url": url,
                    }
                )
    return {"rows": rows, "issues": issues}
