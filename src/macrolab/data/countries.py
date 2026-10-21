"""Enrich a runtime OECD membership list without hard-coding that membership."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import yaml

from macrolab.data.sources.http import SourceClient


def parse_country_metadata(body: bytes) -> dict[str, dict[str, str]]:
    payload = json.loads(body)
    if not isinstance(payload, dict) or "source" not in payload:
        raise ValueError("World Bank rich country metadata has no source object")
    if int(payload.get("pages", 1)) != 1:
        raise ValueError("World Bank country metadata requires additional pages")
    result: dict[str, dict[str, str]] = {}
    for source in payload["source"]:
        for concept in source.get("concept", []):
            if concept.get("id") != "Country":
                continue
            for country in concept.get("variable", []):
                result[str(country["id"])] = {
                    str(item["id"]): str(item["value"])
                    for item in country.get("metatype", [])
                    if item.get("value") is not None
                }
    if not result:
        raise ValueError("World Bank country metadata has no countries")
    return result


def enrich_country_metadata(
    countries: list[dict[str, Any]], client: SourceClient
) -> list[dict[str, Any]]:
    """Preserve the supplied roster and OECD fields; flag missing supplementary metadata."""
    if not countries:
        return []
    notes_config = yaml.safe_load((client.root / "configs/country_notes.yaml").read_text())
    source_codes = sorted({"EMU" if row["iso3"] == "EA" else row["iso3"] for row in countries})
    url = (
        "https://api.worldbank.org/v2/sources/2/country/"
        f"{';'.join(source_codes)}/metadata?format=json&per_page=20000"
    )
    response = client.fetch("WorldBank", "country-rich-metadata", url, "application/json")
    metadata: dict[str, dict[str, str]] = {}
    error: str | None = None
    try:
        if response.record.status != 200 or response.body is None:
            raise ValueError(f"Country metadata unavailable: {response.record.error}")
        metadata = parse_country_metadata(response.body)
    except (ValueError, KeyError, TypeError) as exc:
        error = str(exc)

    ecb_url = notes_config["sources"]["ecb_euro_adoption"]["url"]
    ecb = client.fetch("ECB", "country-euro-adoption-reference", ecb_url, "text/html")
    history_url = notes_config["sources"]["ecb_emu_history"]["url"]
    history = client.fetch("ECB", "country-euro-exact-dates", history_url, "text/html")
    ecb_current = (
        ecb.record.status == 200
        and ecb.body is not None
        and b"Euro since" in ecb.body
        and b"Joining the euro area" in ecb.body
        and history.record.status == 200
        and history.body is not None
        and b"1 January 1999" in history.body
    )
    as_of = str(getattr(client, "as_of_date", notes_config["verified_as_of"]))[:10]
    enriched: list[dict[str, Any]] = []
    for original in countries:
        row = deepcopy(original)
        code = str(row["iso3"])
        provider = metadata.get("EMU" if code == "EA" else code, {})
        issues = list(row.get("metadata_issues", []))
        if error or not provider:
            issues.append({"code": "country_metadata_unavailable", "message": error or code})
        row.setdefault("name", provider.get("ShortName", code))
        row["worldbank_name"] = provider.get("ShortName")
        row["iso2"] = provider.get("2-alphacode") if code != "EA" else "EA"
        row["iso2_status"] = "provider_metadata" if code != "EA" else "internal_aggregate_code"
        row["worldbank_region"] = provider.get("Region")
        row["region"] = row.get("oecd_region")
        row["currency"] = provider.get("CurrencyUnit")
        row["currency_code"] = None
        row["currency_source_url"] = url if row["currency"] else None
        row["country_metadata_source_url"] = url
        row["country_metadata_raw_path"] = response.record.raw_path
        row["notes_status"] = "DRAFT"
        row["notes_review_required"] = True
        row["notes"] = [
            deepcopy(note) for note in notes_config.get("notes", []) if note["country"] == code
        ]
        adoption = notes_config["euro_adoptions"].get(code)
        row["euro_adoption"] = adoption["date"] if adoption else None
        row["monetary_union"] = (
            "EA" if code == "EA" or (adoption and adoption["date"] <= as_of) else None
        )
        # EA is an aggregate of EU members; this flag also routes EU price methodology.
        row["eu_member"] = code == "EA" or code in notes_config["eu_members"]
        row["eu_membership_source_url"] = ecb_url
        row["euro_adoption_source_url"] = history_url if adoption else None
        row["euro_adoption_sources"] = [ecb_url, history_url] if adoption else []
        row["euro_adoption_reference_raw_path"] = history.record.raw_path if adoption else None
        row["euro_metadata_verified_as_of"] = notes_config["verified_as_of"]
        if row["monetary_union"] == "EA":
            row["currency"] = "Euro"
            row["currency_code"] = "EUR"
            row["currency_source_url"] = ecb_url
            row["policy_rate_shared"] = True
            row["default_shock_sample_start"] = max(
                "1999-01-01", row["euro_adoption"] or "1999-01-01"
            )
            row["notes"].append(
                {
                    "country": code,
                    "kind": "monetary_union",
                    "status": "DRAFT",
                    "review_required": True,
                    "text": (
                        f"The euro was adopted on {row['euro_adoption']}; "
                        "the ECB policy rate applies from adoption."
                        if adoption
                        else "The euro-area aggregate uses the common ECB policy rate."
                    ),
                    "source_url": history_url,
                }
            )
        else:
            row["policy_rate_shared"] = False
            row["default_shock_sample_start"] = "1999-01-01"
        if code in notes_config.get("currency_overrides", {}):
            override = notes_config["currency_overrides"][code]
            row["provider_currency_label"] = row["currency"]
            row["currency"] = override["name"]
            row["currency_code"] = override["code"]
            row["currency_source_url"] = notes_config["sources"][override["source"]]["url"]
        if code == "DNK":
            row["fx_regime_note"] = "peg to euro (ERM II)"
        if not row["currency"]:
            issues.append(
                {"code": "currency_unavailable", "message": "Currency metadata is missing."}
            )
        if not row["iso2"]:
            issues.append({"code": "iso2_unavailable", "message": "ISO2 metadata is missing."})
        if not ecb_current:
            issues.append(
                {
                    "code": "euro_metadata_reference_unavailable",
                    "message": "Using dated DRAFT metadata.",
                }
            )
        row["metadata_issues"] = issues
        enriched.append(row)
    return enriched
