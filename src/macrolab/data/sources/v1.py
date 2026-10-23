"""Audited v1 index/rate variants; never replace accepted v0 observations."""

from __future__ import annotations

import calendar
import csv
import io
from collections import defaultdict
from datetime import date
from typing import Any

from macrolab.data.audit import SourceAudit
from macrolab.data.sources.bis import make_row
from macrolab.data.sources.http import FetchResult, SourceClient

PCPS = (
    "https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS,9.0.0/G001.PALLFNF+PNFUEL+PNRG.INDEX.M"
)
POLICY = "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR+MRR_FR+MRR_MBR.LEV"
HICP = "https://data-api.ecb.europa.eu/service/data/HICP/M.U2.Y.000000.4F0.INX"
XML = "application/vnd.sdmx.structurespecificdata+xml;version=2.1"
REQUESTS = {
    "pcps": ("IMF", PCPS + "?startPeriod=1980", "text/csv"),
    "pcps_audit": ("IMF", PCPS + "?startPeriod=1999", XML),
    "policy": ("ECB", POLICY + "?startPeriod=1999-01-01&format=csvdata", "text/csv"),
    "policy_audit": ("ECB", POLICY + "?startPeriod=1999-01-01&format=sdmx-2.1", XML),
    "hicp": ("ECB", HICP + "?format=csvdata", "text/csv"),
    "hicp_audit": ("ECB", HICP + "?format=sdmx-2.1", XML),
}
INDEX_CODES = {"PALLFNF": "all", "PNRG": "energy", "PNFUEL": "nonfuel"}


def csv_rows(response: FetchResult) -> list[dict[str, str]]:
    if response.record.status != 200 or response.body is None or response.record.error:
        raise ValueError(f"Required v1 source unavailable: {response.record.url}")
    return list(csv.DictReader(io.StringIO(response.body.decode("utf-8-sig"))))


def pcps_rows(response: FetchResult) -> list[dict[str, Any]]:
    output = []
    for raw in csv_rows(response):
        code = raw["INDICATOR"]
        if (
            code not in INDEX_CODES
            or raw["COUNTRY"] != "G001"
            or raw["DATA_TRANSFORMATION"] != "INDEX"
            or raw["FREQUENCY"] != "M"
            or raw["SCALE"] != "0"
            or raw.get("ACCESS_SHARING_LEVEL") != "PUBLIC_OPEN"
            or raw.get("ACCESS_SHARING_NOTES", "").strip()
            or raw.get("LICENSE")
            != (
                "© International Monetary Fund Copyright. All Rights Reserved. "
                "https://www.imf.org/external/terms.htm"
            )
            or float(raw["OBS_VALUE"]) <= 0
        ):
            raise ValueError("PCPS definitions/access metadata differ from the reviewed indices")
        variant = INDEX_CODES[code]
        key = f"IMF.RES:PCPS(9.0.0).G001.{code}.INDEX.M"
        row = make_row(
            country="GLOBAL",
            concept="commod_idx",
            source="IMF",
            series_id=key,
            raw=raw,
            fetched=response,
            parser="csv",
            selector={
                k: raw[k] for k in ("COUNTRY", "INDICATOR", "DATA_TRANSFORMATION", "FREQUENCY")
            },
            unit="index",
            frequency="M",
            sa_flag="NSA",
            price_basis="nominal",
            base_year="2016",
        )
        row.update(
            variant=variant,
            shared=True,
            default_transform="yoy_pct",
            quarterly_aggregation="mean",
            attribution=(
                "Source: International Monetary Fund, Primary Commodity Prices, "
                "https://data.imf.org/en/datasets/IMF.RES:PCPS. "
                f"{code}, 2016=100; accessed {response.record.retrieved_utc}. "
                "Non-commercial research and teaching; "
                "MacroLab transformations identified separately."
            ),
            terms_status="allowed: non-commercial IMF statistical-data terms; indices only",
        )
        output.append(row)
    if {r["variant"] for r in output} != {"all", "energy", "nonfuel"}:
        raise ValueError("One of the required PCPS index variants is missing")
    return output


def policy_rows(response: FetchResult, as_of: date) -> list[dict[str, Any]]:
    """Select actual published calendar month-end values; never forward-fill."""
    output = []
    seen = set()
    for raw in csv_rows(response):
        when = date.fromisoformat(raw["TIME_PERIOD"])
        if when > as_of or when.day != calendar.monthrange(when.year, when.month)[1]:
            continue  # An incomplete current month is not an observed month-end.
        instrument = raw["PROVIDER_FM_ID"]
        if instrument not in {"DFR", "MRR_FR", "MRR_MBR"} or raw["UNIT"] != "PCPA":
            raise ValueError("Unexpected ECB policy-rate definition")
        variant = "dfr" if instrument == "DFR" else "mro"
        period = when.strftime("%Y-%m")
        if (variant, period) in seen:
            raise ValueError("ECB MRO tender regimes overlap; manual source review required")
        seen.add((variant, period))
        row = make_row(
            country="EA",
            concept="policy_rate",
            source="ECB",
            series_id=raw["KEY"],
            raw=raw,
            fetched=response,
            parser="csv",
            selector={
                k: raw[k]
                for k in (
                    "FREQ",
                    "REF_AREA",
                    "CURRENCY",
                    "PROVIDER_FM",
                    "INSTRUMENT_FM",
                    "PROVIDER_FM_ID",
                    "DATA_TYPE_FM",
                )
            },
            unit="percent",
            frequency="M",
            sa_flag="NA",
            price_basis="not_applicable",
            flags=["monthly_end_of_period", "shared_ecb_rate"],
        )
        row.update(
            date=period,
            variant=variant,
            shared=True,
            source_geo="EA",
            aggregation="published calendar month-end; quarterly mean of monthly endpoints",
            terms_status="allowed with ECB attribution; modifications identified",
            attribution=(
                f"Source: European Central Bank, {raw['TITLE_COMPL']}; "
                f"{response.record.url}; accessed {response.record.retrieved_utc}. "
                "MacroLab selects published month-end daily observations without filling."
            ),
        )
        output.append(row)
    if {r["variant"] for r in output} != {"dfr", "mro"}:
        raise ValueError("Required ECB policy variants are missing")
    return output


def hicp_rows(response: FetchResult) -> list[dict[str, Any]]:
    output = []
    for raw in csv_rows(response):
        if (
            raw["KEY"] != "HICP.M.U2.Y.000000.4F0.INX"
            or raw["UNIT_INDEX_BASE"] != "2025 = 100"
            or raw["UNIT"] != "IX"
        ):
            raise ValueError("ECB HICP series/base differs from reviewed current flow")
        row = make_row(
            country="EA",
            concept="cpi",
            source="ECB",
            series_id=raw["KEY"],
            raw=raw,
            fetched=response,
            parser="csv",
            selector={
                k: raw[k]
                for k in (
                    "FREQ",
                    "REF_AREA",
                    "ADJUSTMENT",
                    "ICP_ITEM",
                    "DATA_PROVIDER",
                    "ICP_SUFFIX",
                )
            },
            unit="index",
            frequency="M",
            sa_flag="SA",
            price_basis="nominal",
            base_year="2025",
            flags=["HICP", "working_day_adjusted", "euro_area_changing_composition", "ECOICOP2"],
        )
        row.update(
            variant="hicp_sa",
            methodology="HICP",
            terms_status="allowed with ECB attribution; official seasonal adjustment",
            attribution=(
                f"Source: European Central Bank, {raw['TITLE_COMPL']}; "
                f"{response.record.url}; accessed {response.record.retrieved_utc}. "
                "Seasonal adjustment by ECB; growth/frequency calculations by MacroLab."
            ),
        )
        output.append(row)
    if not output:
        raise ValueError("Current ECB seasonally adjusted HICP is missing")
    return output


def exact_audit(
    root: Any, rows: list[dict[str, Any]], references: dict[str, FetchResult]
) -> dict[str, Any]:
    """Compare CSV selections with a separate official SDMX response/parser."""
    reader = SourceAudit(root)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["variant"]].append(row)
    checks = []
    for variant, values in sorted(grouped.items()):
        family = (
            "pcps"
            if values[0]["concept_id"] == "commod_idx"
            else "hicp"
            if variant == "hicp_sa"
            else "policy"
        )
        response = references[family + "_audit"]
        if response.record.status != 200 or not response.record.raw_path:
            raise ValueError(f"Missing independent-format reference for {variant}")
        lookup = {r["date"]: r for r in values}
        for when in ("1999-01", "2020-04", max(lookup)):
            row = lookup[when]
            reference_row = {
                **row,
                "raw_path": response.record.raw_path,
                "audit": {**row["audit"], "parser": "sdmx_xml"},
            }
            reference = reader.reference_value(reference_row)
            difference = abs(row["value"] - reference)
            checks.append(
                {
                    "variant": variant,
                    "date": when,
                    "absolute_difference": difference,
                    "matched": difference == 0,
                    "source_url": response.record.url,
                    "source_sha256": response.record.sha256,
                }
            )
    return {
        "passed": all(c["matched"] for c in checks),
        "checks": checks,
        "maximum_absolute_difference": max(c["absolute_difference"] for c in checks),
        "method": (
            "Three dates per variant: CSV adapter versus separately downloaded official "
            "SDMX XML, independently parsed. Same publisher, not an independent measurement."
        ),
    }


def fetch_v1(client: SourceClient, countries: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    responses = {
        name: client.fetch(source, f"v1_{name}", url, mime)
        for name, (source, url, mime) in REQUESTS.items()
    }
    variants = (
        pcps_rows(responses["pcps"])
        + policy_rows(responses["policy"], as_of)
        + hicp_rows(responses["hicp"])
    )
    audit = exact_audit(client.root, variants, responses)
    if not audit["passed"]:
        raise ValueError("Required v1 source audit is not exact")
    defaults = [
        {**row, "country": country["iso3"]}
        for country in countries
        for row in variants
        if row["concept_id"] == "commod_idx" and row["variant"] == "nonfuel"
    ]
    return {"rows": defaults, "variant_rows": variants, "issues": [], "audit": audit}
