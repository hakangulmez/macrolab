"""Non-destructive plausibility, duplicate, gap and special-period flags."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from macrolab.data.standardise import period_ordinal, period_start


def validate(rows: list[dict[str, Any]], rules: dict[str, Any]) -> dict[str, Any]:
    identities: set[tuple[str, str, str, str]] = set()
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    duplicates = []
    outliers = []
    for row in rows:
        identity = (row["country"], row["concept_id"], row["date"], row["freq"])
        if identity in identities:
            duplicates.append(
                {
                    "country": identity[0],
                    "concept_id": identity[1],
                    "date": identity[2],
                    "freq": identity[3],
                }
            )
        identities.add(identity)
        groups[(identity[0], identity[1], identity[3])].append(row)
        low, high = rules["plausibility"].get(row["concept_id"], (None, None))
        if low is not None and not low <= row["value"] <= high:
            row["flags"] = sorted(set(row["flags"] + ["plausibility_outlier"]))
            outliers.append(
                {
                    "country": identity[0],
                    "concept_id": identity[1],
                    "date": identity[2],
                    "code": "plausibility_outlier",
                }
            )
        start = period_start(row["date"], row["freq"])
        if "2020-01-01" <= start <= "2021-06-30":
            row["flags"] = sorted(set(row["flags"] + ["covid_period"]))
        if (
            row["concept_id"] in {"policy_rate", "us_policy_rate"}
            and row["value"] <= rules["elb_threshold_percent"]
        ):
            row["flags"] = sorted(set(row["flags"] + ["elb_period"]))
    gaps = []
    for (country, concept, freq), values in sorted(groups.items()):
        values.sort(key=lambda row: row["date"])
        missing_count = (
            period_ordinal(values[-1]["date"], freq)
            - period_ordinal(values[0]["date"], freq)
            + 1
            - len(values)
        )
        if missing_count:
            gaps.append(
                {
                    "country": country,
                    "concept_id": concept,
                    "freq": freq,
                    "missing_periods": missing_count,
                }
            )
        changes = [values[i]["value"] - values[i - 1]["value"] for i in range(1, len(values))]
        if len(changes) > 8:
            median = statistics.median(changes)
            mad = statistics.median(abs(value - median) for value in changes)
            if mad > 0:
                for row, change in zip(values[1:], changes, strict=True):
                    if abs(change - median) > 12 * mad:
                        row["flags"] = sorted(set(row["flags"] + ["large_observation_change"]))
                        outliers.append(
                            {
                                "country": country,
                                "concept_id": concept,
                                "date": row["date"],
                                "code": "large_observation_change",
                            }
                        )
    if duplicates:
        raise ValueError(f"Harmonised data contains {len(duplicates)} duplicate keys")
    return {
        "observations": len(rows),
        "duplicates": duplicates,
        "gaps": gaps,
        "outlier_flags": outliers,
        "interpolated_observations": 0,
        "outlier_policy": "flag only; all source values retained",
    }
