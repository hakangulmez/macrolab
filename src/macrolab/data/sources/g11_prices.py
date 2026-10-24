"""Narrow G1.1 price refresh with unchanged values and independently auditable sources."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from macrolab.data.sources.bis import fetch_issue
from macrolab.data.sources.eurostat import normalise_eurostat
from macrolab.data.sources.http import FetchResult, SourceClient
from macrolab.data.sources.oecd import XML_ACCEPT, parse_structure, standardise_csv


def configuration() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[4] / "configs/g11_prices.yaml"
    result: dict[str, Any] = yaml.safe_load(path.read_text())
    return result


def cpi_mappings() -> list[dict[str, Any]]:
    common = {
        "price_basis": "consumer_prices",
        "methodology_by_eu": True,
        "preferred_frequency": "M",
        "priority": -1,
    }
    result = []
    for concept, expenditure, methodology in [
        ("cpi", "_T", None),
        ("cpi_core", "_TXCP01_NRG", "N"),
        ("cpi_core", "_TXNRG_01_02", "HICP"),
    ]:
        selector: dict[str, Any] = {
            "FREQ": ["M", "Q"],
            "MEASURE": "CPI",
            "UNIT_MEASURE": "IX",
            "EXPENDITURE": expenditure,
            "ADJUSTMENT": ["S", "N"],
            "TRANSFORMATION": "_Z",
        }
        flags = ["classification_COICOP2018"]
        if methodology:
            selector["METHODOLOGY"] = methodology
        if methodology == "HICP":
            flags.append("excludes_energy_food_alcohol_tobacco")
        result.append(
            {
                **common,
                "concept_id": concept,
                "selector": selector,
                "flags": flags,
                "definition": (
                    "OECD COICOP2018 headline index; HICP for EU/EA, national CPI otherwise."
                    if concept == "cpi"
                    else "OECD COICOP2018 core index: national excludes food/energy; EU/EA HICP "
                    "excludes energy, food, alcohol and tobacco."
                ),
            }
        )
    return result


def normalise_ppi_eurostat(
    payload: dict[str, Any],
    fetched: FetchResult,
    countries: list[dict[str, Any]],
    specification: dict[str, Any],
) -> list[dict[str, Any]]:
    """Verify actual dimensions before applying the declared metadata."""
    for dimension, expected in specification["filters"].items():
        actual = (
            payload.get("dimension", {}).get(dimension, {}).get("category", {}).get("index", {})
        )
        codes = set(actual) if isinstance(actual, (dict, list)) else set()
        if codes != {expected}:
            raise ValueError(f"Eurostat PPI dimension {dimension} differs from verified selection")
    eligible = [
        c
        for c in countries
        if c.get("eu_member") is True
        or c["iso3"] == "EA"
        or c["iso3"] in specification.get("additional_countries", [])
    ]
    rows = normalise_eurostat(payload, fetched, eligible, specification)
    for row in rows:
        row["definition"] = specification["definition"]
        row["unit_label"] = "Index, 2021=100"
        row["source_adjustment"] = "NSA"
        row["market_scope"] = "domestic"
        row["activity"] = "NACE Rev. 2 C (manufacturing)"
    return rows


def _usable(fetched: FetchResult) -> bool:
    return (
        fetched.record.status == 200 and fetched.record.body_complete and fetched.body is not None
    )


def fetch_prices(client: SourceClient, countries: list[dict[str, Any]]) -> dict[str, Any]:
    """Return additive CPI/core/PPI candidates; no fetch modifies the prior snapshot."""
    config = configuration()
    output: dict[str, Any] = {"rows": [], "issues": [], "requests": [], "source_details": {}}

    def fetch(source: str, identifier: str, url: str, accept: str) -> FetchResult:
        result = client.fetch(source, identifier, url, accept)
        output["requests"].append(asdict(result.record))
        if not _usable(result):
            output["issues"].append(fetch_issue(source, identifier, result))
        return result

    cpi = config["oecd_cpi"]
    metadata = fetch("OECD", "g11_cpi2018_metadata", cpi["metadata_url"], XML_ACCEPT)
    if _usable(metadata):
        try:
            assert metadata.body is not None
            structure = parse_structure(metadata.body)
            if structure["dimensions"] != cpi["dimensions"]:
                raise ValueError("OECD COICOP2018 dimension order changed")
            for dimension, codes in cpi["verified_codes"].items():
                for code, label in codes.items():
                    if structure["labels"][dimension].get(code) != label:
                        raise ValueError(f"OECD COICOP2018 definition changed: {dimension}/{code}")
            fetched = fetch("OECD", "g11_cpi2018_data", cpi["data_url"], "text/csv")
            if _usable(fetched):
                assert fetched.body is not None
                rows, issues = standardise_csv(
                    fetched.body,
                    cpi,
                    cpi_mappings(),
                    structure,
                    countries,
                    source_url=fetched.record.url,
                    raw_path=fetched.record.raw_path,
                )
                output["rows"].extend(rows)
                output["issues"].extend(issues)
        except (ValueError, KeyError, ET.ParseError) as error:
            output["issues"].append(
                {"source": "OECD", "code": "g11_price_mapping_failed", "reason": str(error)}
            )
    ppi = config["eurostat_ppi"]
    fetched = fetch("Eurostat", "g11_ppi_domestic", ppi["data_url"], "application/json")
    if _usable(fetched):
        try:
            assert fetched.body is not None
            output["rows"].extend(
                normalise_ppi_eurostat(json.loads(fetched.body), fetched, countries, ppi)
            )
        except (ValueError, KeyError, TypeError) as error:
            output["issues"].append(
                {"source": "Eurostat", "code": "g11_price_mapping_failed", "reason": str(error)}
            )
    coverage: dict[str, dict[str, str]] = {}
    for row in output["rows"]:
        key = row["country"] + "/" + row["concept_id"] + "/" + row["source"] + "/" + row["freq"]
        if key not in coverage:
            coverage[key] = {"first": row["date"], "last": row["date"]}
        coverage[key]["first"] = min(coverage[key]["first"], row["date"])
        coverage[key]["last"] = max(coverage[key]["last"], row["date"])
    output["source_details"] = {
        "mapping_config": "configs/g11_prices.yaml",
        "coverage": dict(sorted(coverage.items())),
        "oecd_ppi_discovery": config["oecd_ppi"],
        "policy": "Price-only candidates; no values spliced across definitions or sources.",
    }
    covered = {(row["country"], row["concept_id"]) for row in output["rows"]}
    for country in countries:
        for concept in ("cpi", "cpi_core", "ppi"):
            if (country["iso3"], concept) not in covered:
                output["issues"].append(
                    {
                        "source": "G1.1 prices",
                        "country": country["iso3"],
                        "concept_id": concept,
                        "code": "no_additional_verified_price_candidate",
                        "reason": (
                            "No matching price refresh observation; "
                            "retain explicitly limited prior candidates."
                        ),
                    }
                )
    return output
