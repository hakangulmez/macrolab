"""BIS official series, preserving source frequency, units and raw audit locations."""

from __future__ import annotations

import csv
import io
import math
import xml.etree.ElementTree as ET
from typing import Any

from macrolab.data.sources.http import FetchResult, SourceClient


def finite(value: Any) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (ValueError, TypeError):
        return False


def period(raw: str) -> str:
    """Normalise IMF's monthly marker; retain native Q/A frequency."""
    return raw.replace("-M", "-")


def read_sdmx(body: bytes) -> tuple[list[dict[str, str]], str]:
    """Flatten CSV or SDMX structure-specific XML, including group attributes."""
    if not body.lstrip().startswith(b"<"):
        return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig")))), "csv"
    root = ET.fromstring(body)
    output: list[dict[str, str]] = []
    for dataset in (e for e in root.iter() if e.tag.split("}")[-1] == "DataSet"):
        common = {k: v for k, v in dataset.attrib.items() if not k.startswith("{")}
        groups = [
            {k: v for k, v in e.attrib.items() if not k.startswith("{")}
            for e in dataset
            if e.tag.split("}")[-1] == "Group"
        ]
        for series in (e for e in dataset if e.tag.split("}")[-1] == "Series"):
            attributes = dict(common)
            for group in groups:
                overlap = set(group) & set(series.attrib)
                if overlap and all(group[k] == series.attrib[k] for k in overlap):
                    attributes.update(group)
            attributes.update(series.attrib)
            for observation in series:
                if observation.tag.split("}")[-1] == "Obs":
                    output.append({**attributes, **observation.attrib})
    return output, "sdmx_xml"


def make_row(
    *,
    country: str,
    concept: str,
    source: str,
    series_id: str,
    raw: dict[str, str],
    fetched: FetchResult,
    parser: str,
    selector: dict[str, str],
    unit: str,
    frequency: str,
    sa_flag: str,
    price_basis: str,
    base_year: str | None = None,
    flags: list[str] | None = None,
) -> dict[str, Any]:
    raw_period = raw["TIME_PERIOD"]
    return {
        "country": country,
        "concept_id": concept,
        "source": source,
        "source_series_id": series_id,
        "date": period(raw_period),
        "value": float(raw["OBS_VALUE"]),
        "unit": unit,
        "unit_mult": int(raw.get("UNIT_MULT") or raw.get("SCALE") or 0),
        "sa_flag": sa_flag,
        "price_basis": price_basis,
        "base_year": base_year,
        "freq": frequency,
        "obs_status": raw.get("OBS_STATUS") or raw.get("STATUS") or "not_reported",
        "source_url": fetched.record.url,
        "raw_path": fetched.record.raw_path,
        "attribution": f"{source}, {series_id}; accessed {fetched.record.retrieved_utc}",
        "terms_status": "unverified" if source == "IMF" else "conditional",
        "flags": list(flags or []),
        "audit": {
            "parser": parser,
            "source_period": raw_period,
            "selector": selector,
            "time_column": "TIME_PERIOD",
            "value_column": "OBS_VALUE",
        },
        "source_metadata": {
            key: value for key, value in raw.items() if key not in ("TIME_PERIOD", "OBS_VALUE")
        },
    }


def fetch_issue(source: str, request_id: str, fetched: FetchResult) -> dict[str, Any]:
    return {
        "source": source,
        "code": "source_request_unavailable",
        "request_id": request_id,
        "url": fetched.record.url,
        "http_status": fetched.record.status,
        "reason": fetched.record.error or "Response contained no usable observations",
    }


def fetch_bis(client: SourceClient, countries: list[dict[str, Any]]) -> dict[str, Any]:
    """Fetch national plus EA raw rates; the pipeline performs euro-adoption splicing."""
    country_map = {str(c["iso2"]): str(c["iso3"]) for c in countries if c.get("iso2")}
    country_map["XM"] = "EA"
    source_codes = "+".join(sorted(country_map))
    requests = [
        (
            "policy_rate",
            "WS_CBPOL",
            f"M.{source_codes}",
            ["FREQ", "REF_AREA"],
            "percent",
            "M",
            None,
        ),
        (
            "credit_pnfs",
            "WS_TC",
            f"Q.{source_codes}.P.A.M.770.A",
            [
                "FREQ",
                "BORROWERS_CTY",
                "TC_BORROWERS",
                "TC_LENDERS",
                "VALUATION",
                "UNIT_TYPE",
                "TC_ADJUST",
            ],
            "percent_gdp",
            "Q",
            None,
        ),
        (
            "house_real",
            "WS_SPP",
            f"Q.{source_codes}.R.628",
            ["FREQ", "REF_AREA", "VALUE", "UNIT_MEASURE"],
            "index",
            "Q",
            "2010",
        ),
        (
            "reer",
            "WS_EER",
            f"M.R.B.{source_codes}",
            ["FREQ", "EER_TYPE", "EER_BASKET", "REF_AREA"],
            "index",
            "M",
            "2020",
        ),
        (
            "neer",
            "WS_EER",
            f"M.N.B.{source_codes}",
            ["FREQ", "EER_TYPE", "EER_BASKET", "REF_AREA"],
            "index",
            "M",
            "2020",
        ),
    ]
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for concept, dataset, key, dimensions, unit, frequency, base in requests:
        request_id = f"bis_{concept}"
        url = f"https://stats.bis.org/api/v1/data/{dataset}/{key}?startPeriod=1950"
        fetched = client.fetch(
            "BIS", request_id, url, "application/vnd.sdmx.structurespecificdata+xml;version=2.1"
        )
        if fetched.record.status != 200 or fetched.body is None:
            issues.append(fetch_issue("BIS", request_id, fetched))
            continue
        try:
            raw_rows, parser = read_sdmx(fetched.body)
        except (ValueError, ET.ParseError, UnicodeError) as exc:
            issues.append(
                {
                    "source": "BIS",
                    "code": "parse_failed",
                    "request_id": request_id,
                    "reason": str(exc),
                }
            )
            continue
        seen: set[str] = set()
        for raw in raw_rows:
            area = raw.get("REF_AREA") or raw.get("BORROWERS_CTY")
            if (
                area not in country_map
                or not raw.get("TIME_PERIOD")
                or not finite(raw.get("OBS_VALUE"))
            ):
                continue
            if raw.get("FREQ") != frequency:
                continue
            if concept == "policy_rate" and raw.get("UNIT_MEASURE") != "368":
                continue
            if concept == "credit_pnfs" and any(
                raw.get(k) != v
                for k, v in {
                    "TC_BORROWERS": "P",
                    "TC_LENDERS": "A",
                    "VALUATION": "M",
                    "UNIT_TYPE": "770",
                    "TC_ADJUST": "A",
                }.items()
            ):
                continue
            if concept in ("reer", "neer") and (
                raw.get("EER_BASKET") != "B"
                or raw.get("EER_TYPE") != ("R" if concept == "reer" else "N")
            ):
                continue
            if concept == "house_real" and raw.get("UNIT_MEASURE") != "628":
                continue
            if concept in ("reer", "neer") and raw.get("UNIT_MEASURE") != "882":
                issues.append(
                    {
                        "source": "BIS",
                        "code": "unexpected_index_base",
                        "concept_id": concept,
                        "country": country_map[area],
                        "unit_code": raw.get("UNIT_MEASURE"),
                    }
                )
                continue
            selector = {dim: raw[dim] for dim in dimensions if dim in raw}
            flags = ["seasonal_adjustment_unknown"]
            if concept == "policy_rate":
                flags += ["monthly_end_of_period"]
            if concept == "credit_pnfs":
                flags += ["adjusted_for_breaks", "market_value"]
            if area == "XM":
                flags += ["euro_area_aggregate", "source_composition_as_published"]
            row = make_row(
                country=country_map[area],
                concept=concept,
                source="BIS",
                series_id=f"{dataset}." + ".".join(selector.values()),
                raw=raw,
                fetched=fetched,
                parser=parser,
                selector=selector,
                unit=unit,
                frequency=frequency,
                sa_flag="UNKNOWN",
                price_basis="real" if concept in ("house_real", "reer") else "nominal",
                base_year=base,
                flags=flags,
            )
            rows.append(row)
            seen.add(country_map[area])
            if concept == "policy_rate" and country_map[area] == "USA":
                rows.append(
                    {
                        **row,
                        "country": "GLOBAL",
                        "concept_id": "us_policy_rate",
                        "flags": [*row["flags"], "global_common_factor"],
                    }
                )
        for country in countries:
            if country["iso3"] not in seen:
                issues.append(
                    {
                        "source": "BIS",
                        "code": "series_not_returned",
                        "country": country["iso3"],
                        "concept_id": concept,
                        "url": url,
                    }
                )
    return {"rows": rows, "issues": issues}
