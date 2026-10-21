"""Verify OECD CLI coverage without conflating CLI and confidence indicators."""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from macrolab.data.sources.http import FetchResult, SourceClient
from macrolab.data.sources.oecd import LANG, NS, XML_ACCEPT, parse_structure, standardise_csv


def load_configuration() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[4] / "configs/g11_cli.yaml"
    result: dict[str, Any] = yaml.safe_load(path.read_text())
    return result


def response_body(result: FetchResult) -> bytes:
    if result.record.status != 200 or not result.record.body_complete or result.body is None:
        raise ValueError(f"CLI request unavailable: {result.record.status}; {result.record.error}")
    return result.body


def metadata_evidence(body: bytes, dataset: dict[str, Any]) -> dict[str, Any]:
    root = ET.fromstring(body)
    flows = [
        element
        for element in root.findall(".//s:Dataflow", NS)
        if element.get("id") == dataset["dataflow"] and element.get("agencyID") == dataset["agency"]
    ]
    if len(flows) != 1 or flows[0].get("version") != dataset["version"]:
        raise ValueError("Current OECD CLI flow differs from the verified dataflow/version")
    description = " ".join(
        element.text or ""
        for element in flows[0].findall("c:Description", NS)
        if element.get(LANG) == "en"
    )
    scope = re.search(r"CLIs are calculated for [^.]+\.", description)
    annotations = {
        annotation.findtext("c:AnnotationType", default="", namespaces=NS): annotation.findtext(
            "c:AnnotationText", default="", namespaces=NS
        )
        for annotation in flows[0].findall("c:Annotations/c:Annotation", NS)
    }
    return {
        "dataflow": dataset["flow"],
        "current_version": flows[0].get("version"),
        "official_coverage_statement": scope[0] if scope else None,
        "statement_source_url": dataset["metadata_url"],
        "nonproduction_dataflow_annotation": annotations.get("NonProductionDataflow"),
    }


def parse_cli(
    body: bytes,
    structure: dict[str, Any],
    configuration: dict[str, Any],
    countries: list[dict[str, Any]],
    *,
    raw_path: str | None,
) -> dict[str, Any]:
    """Inspect unrestricted LI variants, then select only the verified headline form."""
    dataset, mapping = configuration["dataset"], configuration["mapping"]
    if structure["dimensions"] != dataset["dimensions"]:
        raise ValueError("CLI dimension order differs from the verified structure")
    for dimension, code in mapping["selector"].items():
        if (
            structure["labels"][dimension].get(code)
            != mapping["verified_code_labels"][dimension][code]
        ):
            raise ValueError(f"CLI code/label changed: {dimension}={code}")
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    required = set(dataset["dimensions"]) | {"DATAFLOW", "TIME_PERIOD", "OBS_VALUE"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("CLI CSV lacks required dimensions")
    observed = list(reader)
    if any(row["FREQ"] != "M" or row["MEASURE"] != "LI" for row in observed):
        raise ValueError(
            "CLI response contains observations outside the requested measure/frequency"
        )
    rows, issues = standardise_csv(
        body,
        dataset,
        [mapping],
        structure,
        countries,
        source_url=dataset["data_url"],
        raw_path=raw_path,
    )
    coverage = []
    for country in countries:
        iso3 = country["iso3"]
        matching = [row for row in rows if row["country"] == iso3]
        source_geographies = (
            {
                row["REF_AREA"]
                for row in observed
                if re.fullmatch(r"EA(?:[0-9]{2})?", row["REF_AREA"])
            }
            if iso3 == "EA"
            else {iso3}
        )
        variants = [row for row in observed if row["REF_AREA"] in source_geographies]
        coverage.append(
            {
                "country": iso3,
                "headline_observations": len(matching),
                "all_variant_observations": len(variants),
                "first_date": min((row["date"] for row in matching), default=None),
                "last_date": max((row["date"] for row in matching), default=None),
                "status": "verified_headline_cli" if matching else "not_observed",
            }
        )
        if not matching:
            reason = (
                "cli_headline_definition_not_observed"
                if variants
                else "cli_not_observed_in_current_oecd_flow"
            )
            issues.append(
                {
                    "source": "OECD",
                    "country": iso3,
                    "concept_id": "cli",
                    "code": reason,
                    "reason_code": reason,
                    "detail": (
                        "The verified monthly LI query leaves methodology, adjustment, "
                        "transformation and geography unrestricted. "
                        + (
                            "Other LI variants exist, but the verified headline definition "
                            "has no observations; no variant was substituted."
                            if variants
                            else "No LI observation was returned for this country/aggregate."
                        )
                        + " This establishes absence in the current queried flow, "
                        "not cessation of historical publication."
                    ),
                    "source_url": dataset["data_url"],
                    "metadata_url": dataset["metadata_url"],
                    "raw_path": raw_path,
                }
            )
    return {
        "rows": rows,
        "issues": issues,
        "mapping_evidence": {
            "query_scope": configuration["evidence"]["broad_query_scope"],
            "all_variant_observations": len(observed),
            "source_geographies": sorted({row["REF_AREA"] for row in observed}),
            "variant_counts": {
                "|".join(key): count
                for key, count in sorted(
                    Counter(
                        (row["ADJUSTMENT"], row["TRANSFORMATION"], row["METHODOLOGY"])
                        for row in observed
                    ).items()
                )
            },
            "observed_methodologies": sorted({row["METHODOLOGY"] for row in observed}),
            "coverage_by_country": coverage,
            "raw_path": raw_path,
            "source_url": dataset["data_url"],
        },
    }


def fetch_cli(client: SourceClient, countries: list[dict[str, Any]]) -> dict[str, Any]:
    """Fetch one current structure and one broad CLI history; never fetch confidence data."""
    configuration = load_configuration()
    dataset = configuration["dataset"]
    requests = []
    try:
        metadata = client.fetch("OECD", "cli_current_metadata", dataset["metadata_url"], XML_ACCEPT)
        requests.append(asdict(metadata.record))
        metadata_body = response_body(metadata)
        evidence = metadata_evidence(metadata_body, dataset)
        structure = parse_structure(metadata_body)
        data = client.fetch("OECD", "cli_all_variants_history", dataset["data_url"], "text/csv")
        requests.append(asdict(data.record))
        result = parse_cli(
            response_body(data), structure, configuration, countries, raw_path=data.record.raw_path
        )
        result["mapping_evidence"].update(
            {
                **evidence,
                "metadata_raw_path": metadata.record.raw_path,
                "metadata_sha256": metadata.record.sha256,
                "data_sha256": data.record.sha256,
                "retrieved_utc": data.record.retrieved_utc,
            }
        )
        result["requests"] = requests
        return result
    except (ValueError, KeyError, UnicodeDecodeError, ET.ParseError) as error:
        return {
            "rows": [],
            "issues": [
                {
                    "source": "OECD",
                    "country": country["iso3"],
                    "concept_id": "cli",
                    "code": "cli_verification_unavailable",
                    "detail": str(error),
                    "source_url": dataset["data_url"],
                }
                for country in countries
            ],
            "mapping_evidence": {"verified": False, "error": str(error)},
            "requests": requests,
        }
