"""Normalise metadata and dates without silently transforming source observations."""

from __future__ import annotations

import math
import re
from typing import Any

REQUIRED = (
    "country",
    "concept_id",
    "source",
    "source_series_id",
    "date",
    "value",
    "unit",
    "unit_mult",
    "sa_flag",
    "price_basis",
    "base_year",
    "freq",
    "obs_status",
)


def normalise_period(value: str, frequency: str) -> str:
    text = str(value).strip()
    if frequency == "Q":
        match = re.fullmatch(r"(\d{4})[- ]?Q([1-4])", text)
        if match:
            return f"{match[1]}-Q{match[2]}"
    if frequency == "M":
        match = re.fullmatch(r"(\d{4})(?:-?M|-)(\d{1,2})(?:-\d{2})?", text)
        if match and 1 <= int(match[2]) <= 12:
            return f"{match[1]}-{int(match[2]):02d}"
    if frequency == "A" and re.fullmatch(r"\d{4}", text):
        return text
    raise ValueError(f"Invalid {frequency} source period: {value}")


def period_ordinal(value: str, frequency: str) -> int:
    period = normalise_period(value, frequency)
    if frequency == "Q":
        return int(period[:4]) * 4 + int(period[-1]) - 1
    if frequency == "M":
        return int(period[:4]) * 12 + int(period[-2:]) - 1
    return int(period)


def period_start(value: str, frequency: str) -> str:
    period = normalise_period(value, frequency)
    if frequency == "Q":
        return f"{period[:4]}-{(int(period[-1]) - 1) * 3 + 1:02d}-01"
    return f"{period}-01" if frequency == "M" else f"{period}-01-01"


def standardise(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    clean: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for index, original in enumerate(rows):
        row = dict(original)
        try:
            missing = [key for key in REQUIRED if key not in row]
            if missing:
                raise ValueError(f"Missing schema fields: {missing}")
            if row["freq"] not in {"M", "Q", "A"}:
                raise ValueError("Native frequency must be M/Q/A")
            row["date"] = normalise_period(str(row["date"]), row["freq"])
            if isinstance(row["value"], bool) or not math.isfinite(float(row["value"])):
                raise ValueError("Observation is not a finite source value")
            row["value"] = float(row["value"])
            multiplier = float(row["unit_mult"])
            if not math.isfinite(multiplier) or not multiplier.is_integer():
                raise ValueError("Unit multiplier must be an integer exponent")
            row["unit_mult"] = int(multiplier)
            for field in ("country", "concept_id", "source", "source_series_id", "unit"):
                if not isinstance(row[field], str) or not row[field].strip():
                    raise ValueError(f"Missing or empty {field}")
            if row["sa_flag"] not in {"SA", "NSA", "NA", "UNKNOWN"}:
                raise ValueError("Unrecognised seasonal-adjustment flag")
            if not row.get("source_url") or not row.get("attribution"):
                raise ValueError("A source URL and per-series attribution are mandatory")
            row["flags"] = sorted(set(row.get("flags", [])))
            if row["sa_flag"] == "UNKNOWN":
                row["flags"] = sorted(set(row["flags"] + ["seasonal_adjustment_unknown"]))
            row["shared"] = bool(row.get("shared", False))
            row["price_basis"] = str(row["price_basis"])
            row["base_year"] = None if row["base_year"] is None else str(row["base_year"])
            row["obs_status"] = str(row["obs_status"] or "not_reported")
            row.setdefault("terms_status", "conditional; no publication approved")
            if row["source"] in {"IMF", "WorldBank"} and not row["terms_status"].startswith(
                "allowed"
            ):
                row["terms_status"] = "unresolved – no redistribution of raw data"
            clean.append(row)
        except (TypeError, ValueError, OverflowError) as exc:
            issues.append(
                {
                    "code": "schema_rejection",
                    "country": row.get("country"),
                    "concept_id": row.get("concept_id"),
                    "source": row.get("source"),
                    "row_index": index,
                    "detail": str(exc),
                }
            )
    return clean, issues
