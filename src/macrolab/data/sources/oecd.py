"""Verified OECD SDMX mappings and dynamically sourced OECD membership.

Every returned value is unchanged from a retained official CSV observation.
Source dimensions and raw paths are retained for independent audit/replay.
"""

from __future__ import annotations

import csv
import io
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from macrolab.data.sources.http import FetchResult, SourceClient

BASE = "https://sdmx.oecd.org/public/rest/v1"
COUNTRIES_URL = f"{BASE}/codelist/OECD/CL_AREA/latest?references=none"
XML_ACCEPT = "application/vnd.sdmx.structure+xml;version=2.1"
NS = {
    "s": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "c": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}
LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def _body(result: FetchResult) -> bytes:
    if result.record.status != 200 or not result.record.body_complete or result.body is None:
        raise ValueError(f"OECD request failed: {result.record.url}: {result.record.error}")
    return result.body


def _name(element: ET.Element) -> str:
    return next(
        (name.text or "" for name in element.findall("c:Name", NS) if name.get(LANG) == "en"),
        "",
    )


def _composition(code: ET.Element) -> list[str]:
    for annotation in code.findall("c:Annotations/c:Annotation", NS):
        if annotation.findtext("c:AnnotationType", namespaces=NS) == "COMP_RULE":
            rule = annotation.findtext("c:AnnotationTitle", default="", namespaces=NS)
            if not re.fullmatch(r"[A-Z]{3}(\+[A-Z]{3})*", rule):
                raise ValueError(f"Unsupported OECD composition rule: {rule}")
            members = rule.split("+")
            if len(members) != len(set(members)):
                raise ValueError("Duplicate country in OECD composition metadata")
            return members
    raise ValueError(f"OECD group {code.get('id')} has no explicit composition rule")


def parse_countries(body: bytes, *, raw_path: str | None = None) -> list[dict[str, Any]]:
    """Use OECD00's composition annotation, never the entire geographic codelist."""
    document = ET.fromstring(body)
    codelists = [
        node
        for node in document.findall(".//s:Codelist", NS)
        if node.get("agencyID") == "OECD" and node.get("id") == "CL_AREA"
    ]
    if len(codelists) != 1:
        raise ValueError("Expected one current OECD CL_AREA codelist")
    codelist = codelists[0]
    codes = {node.attrib["id"]: node for node in codelist.findall("s:Code", NS)}
    if "OECD00" not in codes:
        raise ValueError("Current OECD evolving-composition group is missing")
    members = _composition(codes["OECD00"])
    if any(member not in codes or not _name(codes[member]) for member in members):
        raise ValueError("OECD composition references an unknown or unnamed country")
    ea_codes = [code for code in codes if re.fullmatch(r"EA[1-9][0-9]", code)]
    eu_codes = [code for code in codes if re.fullmatch(r"EU[1-9][0-9]_[0-9]{4}", code)]
    if not ea_codes or not eu_codes:
        raise ValueError("Current European composition metadata is missing")
    ea_code = max(ea_codes, key=lambda value: int(value[2:]))
    eu_code = max(eu_codes, key=lambda value: (int(value.split("_")[1]), int(value[2:4])))
    ea_members = _composition(codes[ea_code])
    eu_members = _composition(codes[eu_code])
    regions = {
        group: _composition(codes[group])
        for group in ("OECDA", "OECDE", "OECDSO")
        if group in codes
    }
    countries: list[dict[str, Any]] = []
    for member in sorted(members):
        region_codes = [
            group for group, group_members in regions.items() if member in group_members
        ]
        region = _name(codes[region_codes[0]]) if len(region_codes) == 1 else None
        countries.append(
            {
                "iso3": member,
                "name": _name(codes[member]),
                "group": "member",
                "oecd_region": region,
                "oecd_region_code": region_codes[0] if len(region_codes) == 1 else None,
                "currency": "EUR" if member in ea_members else None,
                "eu_member": member in eu_members,
                "monetary_union": "EA" if member in ea_members else None,
                "membership_source_url": COUNTRIES_URL,
                "membership_group": "OECD00",
                "membership_metadata_version": codelist.get("version"),
                "membership_raw_path": raw_path,
            }
        )
    countries.append(
        {
            "iso3": "EA",
            "name": "Euro area",
            "group": "aggregate",
            "oecd_region": None,
            "currency": "EUR",
            "eu_member": True,
            "monetary_union": "EA",
            "current_euro_area_code": ea_code,
            "euro_area_members": ea_members,
            "membership_source_url": COUNTRIES_URL,
            "membership_group": ea_code,
            "membership_metadata_version": codelist.get("version"),
            "membership_raw_path": raw_path,
        }
    )
    return countries


def fetch_countries(client: SourceClient) -> list[dict[str, Any]]:
    result = client.fetch("OECD", "oecd_membership", COUNTRIES_URL, XML_ACCEPT)
    return parse_countries(_body(result), raw_path=result.record.raw_path)


def parse_structure(body: bytes) -> dict[str, Any]:
    """Resolve dimensions to their exact referenced codelists and English labels."""
    root = ET.fromstring(body)
    structures = root.findall(".//s:DataStructure", NS)
    if len(structures) != 1:
        raise ValueError("Expected exactly one OECD data structure")
    dimensions = sorted(
        structures[0].findall("s:DataStructureComponents/s:DimensionList/s:Dimension", NS),
        key=lambda dimension: int(dimension.attrib["position"]),
    )
    codelists = {
        (node.get("agencyID"), node.get("id"), node.get("version")): node
        for node in root.findall(".//s:Codelist", NS)
    }
    labels: dict[str, dict[str, str]] = {}
    for dimension in dimensions:
        ref = dimension.find(".//s:Enumeration/Ref", NS)
        if ref is None:
            raise ValueError(f"No codelist for OECD dimension {dimension.get('id')}")
        codelist = codelists.get((ref.get("agencyID"), ref.get("id"), ref.get("version")))
        if codelist is None:
            raise ValueError(f"Missing referenced OECD codelist {ref.attrib}")
        labels[dimension.attrib["id"]] = {
            node.attrib["id"]: _name(node) for node in codelist.findall("s:Code", NS)
        }
    return {"dimensions": [dim.attrib["id"] for dim in dimensions], "labels": labels}


def load_mappings() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[4]
    with (root / "configs/oecd_mappings.yaml").open(encoding="utf-8") as handle:
        result: dict[str, Any] = yaml.safe_load(handle)
    return result


def _matches(row: dict[str, str], selector: dict[str, Any]) -> bool:
    return all(
        row.get(key) in (value if isinstance(value, list) else [value])
        for key, value in selector.items()
    )


def standardise_csv(
    body: bytes,
    dataset: dict[str, Any],
    mappings: list[dict[str, Any]],
    structure: dict[str, Any],
    countries: list[dict[str, Any]],
    *,
    source_url: str,
    raw_path: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Retain independent series candidates; never splice adjustments or compositions."""
    lookup = {country["iso3"]: country for country in countries}
    current_ea = lookup.get("EA", {}).get("current_euro_area_code")
    rows: list[dict[str, Any]] = []
    invalid = 0
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    dimensions = structure["dimensions"]
    required = set(dimensions) | {"DATAFLOW", "TIME_PERIOD", "OBS_VALUE"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("OECD CSV is missing required source dimensions or observations")
    for original in reader:
        source_geo = original["REF_AREA"]
        country = "EA" if re.fullmatch(r"EA(?:[0-9]{2})?", source_geo) else source_geo
        if country not in lookup:
            continue
        for mapping in mappings:
            if not _matches(original, mapping["selector"]):
                continue
            if mapping.get("methodology_by_eu"):
                expected = "HICP" if country == "EA" or lookup[country].get("eu_member") else "N"
                if original.get("METHODOLOGY") != expected:
                    continue
            try:
                value = float(original["OBS_VALUE"])
                if not math.isfinite(value):
                    raise ValueError("Non-finite value")
                multiplier = int(original.get("UNIT_MULT") or 0)
                period = original["TIME_PERIOD"]
                expected_period = {
                    "M": r"[0-9]{4}-(?:0[1-9]|1[0-2])",
                    "Q": r"[0-9]{4}-Q[1-4]",
                    "A": r"[0-9]{4}",
                }
                if not re.fullmatch(expected_period[original["FREQ"]], period):
                    raise ValueError("Unexpected period format")
            except (ValueError, KeyError):
                invalid += 1
                continue
            adjustment = original.get("ADJUSTMENT", "_Z")
            flags = list(mapping.get("flags", []))
            priority = int(mapping.get("priority", 0))
            if original.get("METHODOLOGY") == "HICP":
                flags.append("HICP")
            if mapping.get("preferred_frequency", original["FREQ"]) != original["FREQ"]:
                flags.append("native_frequency_differs_from_catalogue")
                priority += 5
            sa_flag = (
                "SA" if adjustment in {"Y", "S"} else "NSA" if adjustment in {"N", "W"} else "NA"
            )
            if sa_flag == "NSA":
                flags.append("not_seasonally_adjusted")
                priority += 2
            if adjustment == "AA":
                flags.append("amplitude_adjusted")
            if not original.get("UNIT_MULT"):
                flags.append("unit_multiplier_not_reported")
            if country == "EA" and source_geo != current_ea:
                flags.append("aggregate_composition_differs_from_current_euro_area")
                priority += 20
            selector = {
                "DATAFLOW": original["DATAFLOW"],
                **{key: original[key] for key in dimensions},
            }
            series_key = ".".join(original[key] for key in dimensions)
            rows.append(
                {
                    "country": country,
                    "concept_id": mapping["concept_id"],
                    "source": "OECD",
                    "source_series_id": f"{dataset['flow']}/{series_key}",
                    "date": period,
                    "value": value,
                    "unit": original["UNIT_MEASURE"],
                    "unit_label": structure["labels"]["UNIT_MEASURE"].get(
                        original["UNIT_MEASURE"], ""
                    ),
                    "unit_mult": multiplier,
                    "source_unit_mult": original.get("UNIT_MULT", ""),
                    "sa_flag": sa_flag,
                    "source_adjustment": adjustment,
                    "price_basis": mapping["price_basis"],
                    "source_price_base": original.get("PRICE_BASE"),
                    "base_year": original.get("REF_YEAR_PRICE") or original.get("BASE_PER") or None,
                    "freq": original["FREQ"],
                    "obs_status": original.get("OBS_STATUS", ""),
                    "source_geo": source_geo,
                    "methodology": original.get("METHODOLOGY"),
                    "source_url": source_url,
                    "raw_path": raw_path,
                    "attribution": "OECD Data Explorer; " + dataset["title"],
                    "terms_status": "local_only_publication_requires_owner_approval",
                    "flags": flags,
                    "candidate_priority": priority,
                    "definition": mapping["definition"],
                    "audit": {
                        "parser": "csv",
                        "time_column": "TIME_PERIOD",
                        "value_column": "OBS_VALUE",
                        "source_period": period,
                        "selector": selector,
                    },
                }
            )
    issues = []
    if invalid:
        issues.append(
            {
                "source": "OECD",
                "code": "invalid_source_observation",
                "dataset": dataset["id"],
                "count": invalid,
                "message": ("Invalid source observations were not published; raw source retained."),
            }
        )
    return rows, issues


def fetch_oecd(
    client: SourceClient, countries: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    countries = fetch_countries(client) if countries is None else countries
    configuration = load_mappings()
    output: dict[str, Any] = {"countries": countries, "rows": [], "issues": [], "requests": []}
    for dataset in configuration["datasets"]:
        relevant = [
            mapping for mapping in configuration["mappings"] if mapping["dataset"] == dataset["id"]
        ]
        try:
            metadata = client.fetch(
                "OECD", f"oecd_{dataset['id']}_metadata", dataset["metadata_url"], XML_ACCEPT
            )
            output["requests"].append(asdict(metadata.record))
            structure = parse_structure(_body(metadata))
            if structure["dimensions"] != dataset["dimensions"]:
                raise ValueError("OECD dimension order changed from verified mapping")
            for mapping in relevant:
                for dimension, values in mapping["selector"].items():
                    for value in values if isinstance(values, list) else [values]:
                        if value not in structure["labels"][dimension]:
                            raise ValueError(f"Unknown OECD source code {dimension}={value}")
            for index, url in enumerate(dataset["data_urls"]):
                fetched = client.fetch(
                    "OECD", f"oecd_{dataset['id']}_data_{index}", url, "text/csv"
                )
                output["requests"].append(asdict(fetched.record))
                rows, issues = standardise_csv(
                    _body(fetched),
                    dataset,
                    relevant,
                    structure,
                    countries,
                    source_url=url,
                    raw_path=fetched.record.raw_path,
                )
                output["rows"].extend(rows)
                output["issues"].extend(issues)
        except (ValueError, ET.ParseError, UnicodeDecodeError) as error:
            output["issues"].append(
                {
                    "source": "OECD",
                    "code": "dataset_unavailable",
                    "dataset": dataset["id"],
                    "message": str(error),
                }
            )
    covered = {(row["country"], row["concept_id"]) for row in output["rows"]}
    concepts = {mapping["concept_id"] for mapping in configuration["mappings"]}
    for country in countries:
        for concept in sorted(concepts):
            if (country["iso3"], concept) not in covered:
                output["issues"].append(
                    {
                        "source": "OECD",
                        "code": "missing_coverage",
                        "country": country["iso3"],
                        "concept_id": concept,
                        "message": ("No verified OECD series match; no interpolation."),
                    }
                )
    return output
