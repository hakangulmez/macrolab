"""Seeded, offline G0 checks using explicitly synthetic quarterly observations.

These checks exercise the scaffold only. They do not estimate or validate any
of the economic models planned for G2, and the fixture represents no country.
"""

import hashlib
import json
import math
import random
import re
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from macrolab import __version__
from macrolab.catalogue import catalogue_summary, project_root

DEFAULT_SEED = 20261020
DEFAULT_PERIODS = 80
DEFAULT_START = "1999-Q1"
SYNTHETIC_COUNTRIES = ("SYN_A", "SYN_B")
SYNTHETIC_CONCEPTS = ("gdp_real", "cpi", "policy_rate")
SYNTHETIC_UNITS = {
    "gdp_real": "synthetic_index",
    "cpi": "synthetic_index",
    "policy_rate": "percent",
}


class ObservationError(ValueError):
    """Synthetic observations cannot support a valid smoke result."""


@dataclass(frozen=True)
class Observation:
    country: str
    concept_id: str
    date: str
    value: float
    unit: str
    frequency: str = "Q"
    source: str = "synthetic"


def canonical_json(value: Any) -> str:
    """Use one stable representation, rejecting NaN and Infinity."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def quarter_labels(start: str, periods: int) -> tuple[str, ...]:
    match = re.fullmatch(r"([1-9][0-9]{3})-Q([1-4])", start)
    if match is None:
        raise ValueError("Sample start must be a quarterly label such as 1999-Q1.")
    if isinstance(periods, bool) or not isinstance(periods, int) or not 1 <= periods <= 120:
        raise ValueError("Synthetic periods must be an integer from 1 to 120.")
    year, quarter = (int(part) for part in match.groups())
    first = year * 4 + quarter - 1
    if (first + periods - 1) // 4 > 9999:
        raise ValueError("Synthetic sample extends past the supported four-digit year range.")
    return tuple(f"{value // 4:04d}-Q{value % 4 + 1}" for value in range(first, first + periods))


def generate_observations(
    *, seed: int = DEFAULT_SEED, periods: int = DEFAULT_PERIODS, start: str = DEFAULT_START
) -> tuple[Observation, ...]:
    """Generate toy data with no economic or empirical interpretation."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("Synthetic seed must be an integer.")
    dates = quarter_labels(start, periods)
    rng = random.Random(seed)
    observations: list[Observation] = []
    for country_index, country in enumerate(SYNTHETIC_COUNTRIES):
        for concept_id in SYNTHETIC_CONCEPTS:
            for index, date in enumerate(dates):
                if concept_id == "policy_rate":
                    value = 2.0 + country_index * 0.5 + rng.uniform(-0.75, 0.75)
                else:
                    value = 100.0 + country_index * 5.0 + index * 0.4 + rng.uniform(-0.25, 0.25)
                observations.append(
                    Observation(
                        country=country,
                        concept_id=concept_id,
                        date=date,
                        value=round(value, 8),
                        unit=SYNTHETIC_UNITS[concept_id],
                    )
                )
    return tuple(observations)


def validate_observations(observations: tuple[Observation, ...]) -> None:
    if not observations:
        raise ObservationError("No synthetic observations were supplied.")
    seen: set[tuple[str, str, str, str]] = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, Observation):
            raise ObservationError(f"Observation {index} is not an Observation record.")
        label = f"{observation.country}/{observation.concept_id}/{observation.date}"
        if observation.country not in SYNTHETIC_COUNTRIES:
            raise ObservationError(f"{label}: expected a fictional SYN_A or SYN_B economy.")
        if observation.concept_id not in SYNTHETIC_CONCEPTS:
            raise ObservationError(f"{label}: unknown synthetic concept.")
        if re.fullmatch(r"[1-9][0-9]{3}-Q[1-4]", observation.date) is None:
            raise ObservationError(f"{label}: invalid quarterly date.")
        if observation.frequency != "Q" or observation.source != "synthetic":
            raise ObservationError(f"{label}: expected quarterly, explicitly synthetic data.")
        if observation.unit != SYNTHETIC_UNITS[observation.concept_id]:
            raise ObservationError(f"{label}: incorrect unit for the synthetic concept.")
        if (
            isinstance(observation.value, bool)
            or not isinstance(observation.value, (int, float))
            or not math.isfinite(observation.value)
        ):
            raise ObservationError(f"{label}: value must be a finite number.")
        if observation.concept_id in {"gdp_real", "cpi"} and observation.value <= 0:
            raise ObservationError(f"{label}: synthetic index values must be positive.")
        key = (observation.country, observation.concept_id, observation.date, observation.frequency)
        if key in seen:
            raise ObservationError(f"{label}: duplicate observation.")
        seen.add(key)


def summarize_observations(
    observations: tuple[Observation, ...], *, start: str, periods: int
) -> list[dict[str, Any]]:
    """Report the actual sample; reject gaps or extra dates instead of filling them."""
    validate_observations(observations)
    expected_dates = set(quarter_labels(start, periods))
    summaries: list[dict[str, Any]] = []
    for country in SYNTHETIC_COUNTRIES:
        for concept_id in SYNTHETIC_CONCEPTS:
            group = sorted(
                (
                    row
                    for row in observations
                    if row.country == country and row.concept_id == concept_id
                ),
                key=lambda row: row.date,
            )
            actual_dates = {row.date for row in group}
            if actual_dates != expected_dates:
                missing = sorted(expected_dates - actual_dates)
                extra = sorted(actual_dates - expected_dates)
                raise ObservationError(
                    f"{country}/{concept_id}: sample mismatch; missing={missing}, extra={extra}."
                )
            values = [row.value for row in group]
            summaries.append(
                {
                    "country": country,
                    "concept_id": concept_id,
                    "unit": group[0].unit,
                    "observations": len(group),
                    "actual_sample": {"start": group[0].date, "end": group[-1].date},
                    "mean": statistics.mean(values),
                    "min": min(values),
                    "max": max(values),
                }
            )
    return summaries


def build_smoke_summary(
    *, seed: int = DEFAULT_SEED, periods: int = DEFAULT_PERIODS
) -> dict[str, Any]:
    """Build deterministic evidence; elapsed runtime is added by the CLI runner."""
    observations = generate_observations(seed=seed, periods=periods)
    dates = quarter_labels(DEFAULT_START, periods)
    config = {
        "fixture_version": 1,
        "synthetic": True,
        "seed": seed,
        "countries": list(SYNTHETIC_COUNTRIES),
        "concepts": list(SYNTHETIC_CONCEPTS),
        "frequency": "Q",
        "periods": periods,
        "sample": {"start": DEFAULT_START, "end": dates[-1]},
    }
    result: dict[str, Any] = {
        "status": "passed",
        "gate": "G0",
        "synthetic": True,
        "label": "Synthetic scaffold check; no economic model has been estimated",
        "snapshot_id": "synthetic_fixture_v1",
        "code_version": __version__,
        "seed": seed,
        "config": config,
        "config_hash": content_hash(config),
        "observations_hash": content_hash([asdict(row) for row in observations]),
        "catalogue": catalogue_summary(),
        "counts": {
            "economies": len(SYNTHETIC_COUNTRIES),
            "concepts": len(SYNTHETIC_CONCEPTS),
            "series": len(SYNTHETIC_COUNTRIES) * len(SYNTHETIC_CONCEPTS),
            "observations": len(observations),
            "quarters_per_series": periods,
        },
        "actual_sample": {"start": dates[0], "end": dates[-1], "frequency": "Q"},
        "series_summaries": summarize_observations(
            observations, start=DEFAULT_START, periods=periods
        ),
        "limitations": [
            "Fictional economies and synthetic observations; no real-country results.",
            "Source mappings and real-data validation are deferred to G1.",
            "No economic model implementation or model validation is included at G0.",
        ],
    }
    result["summary_hash"] = content_hash(result)
    return result


def run_quick(*, seed: int = DEFAULT_SEED, periods: int = DEFAULT_PERIODS) -> dict[str, Any]:
    started = time.perf_counter()
    result = build_smoke_summary(seed=seed, periods=periods)
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    output_path: Path = project_root() / "runs" / "quick" / "summary.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    return result
