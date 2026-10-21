"""Read local browser bundles and prepare honest, regular common samples."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from macrolab.analysis.transforms import apply_transform, label, period_frequency, period_index
from macrolab.models.base import AnalysisData, check

FREQUENCY_RANK = {"M": 0, "Q": 1, "A": 2}


def input_fingerprint(value: Any) -> str:
    """Hash JSON inputs, treating integer-valued floats as equivalent JSON numbers.

    JavaScript JSON transport can render 1.0 as 1. This normalisation preserves
    numeric source values without rounding nonintegral values or computed outputs.
    """

    def normalise(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: normalise(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalise(val) for val in item]
        if isinstance(item, float) and item.is_integer():
            return int(item)
        return item

    payload = json.dumps(normalise(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def snapshot_bundle(
    snapshot_id: str,
    countries: list[str],
    concepts: list[str],
    root: Path | None = None,
) -> dict[str, Any]:
    """Read a validated local JSON vintage, without network or Parquet dependencies."""
    root = root or Path(__file__).resolve().parents[3]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", snapshot_id):
        raise ValueError("Invalid stored snapshot ID")
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]{1,11}", country) for country in countries):
        raise ValueError("Invalid country bundle identifier")
    directory = root / "data/processed/current"
    manifest = json.loads((directory / "processed_manifest.json").read_text())
    if manifest["snapshot_id"] != snapshot_id:
        marker = json.loads((root / "data/manifests/snapshots" / f"{snapshot_id}.json").read_text())
        directory = (root / marker["processed_manifest"]).parent
        if not directory.resolve().is_relative_to((root / "data/processed").resolve()):
            raise ValueError("Snapshot must remain inside local processed data")
        manifest = json.loads((directory / "processed_manifest.json").read_text())
    if manifest["snapshot_id"] != snapshot_id or not manifest["validation_passed"]:
        raise ValueError("Snapshot identity or validation does not match")
    bundle: dict[str, Any] = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "as_of_date": manifest["as_of_date"],
        "countries": {},
    }
    for country in countries:
        source = json.loads((directory / "browser" / f"{country}.json").read_text())
        if source["snapshot_id"] != snapshot_id or source["country"]["iso3"] != country:
            raise ValueError("Country bundle identity does not match the requested vintage")
        cards = {c["concept_id"]: c for c in source["cards"]}
        bundle["countries"][country] = {
            "metadata": source["country"],
            "series": {
                cid: {
                    "metadata": cards.get(cid, {"concept_id": cid, "status": "missing"}),
                    "observations": source["series"].get(cid, []),
                }
                for cid in concepts
            },
        }
    return bundle


def _convert(
    x: pd.Series[Any],
    native: str,
    target: str,
    method: str | None,
    card: dict[str, Any],
) -> tuple[pd.Series[Any], dict[str, Any]]:
    index = period_index(x)
    if native not in FREQUENCY_RANK or target not in FREQUENCY_RANK:
        raise ValueError("Frequency must be M, Q or A")
    detail: dict[str, Any] = {
        "from": native,
        "to": target,
        "method": "none",
        "incomplete_periods": [],
        "required_observations": 1,
    }
    if native == target:
        return x, detail
    if FREQUENCY_RANK[native] > FREQUENCY_RANK[target]:
        raise ValueError("Disaggregation to a higher frequency is unavailable in v0")
    if method not in {"mean", "sum", "last"}:
        raise ValueError("Choose an explicit mean, last or sum frequency-conversion rule")
    segments = card.get("source_segments", [])
    signatures = {
        tuple(str(s.get(k)) for k in ("unit", "unit_mult", "price_basis", "base_year", "sa_flag"))
        for s in segments
    }
    if len(signatures) > 1:
        raise ValueError("Frequency conversion cannot combine incompatible units or adjustments")
    rules = card.get("aggregation_rules", {})
    if method == "last":
        paths = ["monthly_to_quarterly"] if native == "M" else ["quarterly_to_annual"]
        if native == "M" and target == "A":
            paths.append("quarterly_to_annual")
        if any("last" not in rules.get(path, {}).get("optional", []) for path in paths):
            raise ValueError(
                "End-of-period aggregation is permitted only for verified stock series"
            )
    if method == "sum":
        currencies = {"XDC", "NCU", "USD", "EUR", "CURRENCY", "NATIONAL_CURRENCY"}
        actual_flow = (
            native == "Q"
            and target == "A"
            and card.get("verified_period_flow") is True
            and rules.get("quarterly_to_annual", {}).get("conditional_sum_allowed") is True
            and bool(segments)
            and all(str(s.get("unit", "")).upper() in currencies for s in segments)
        )
        flags = [str(v).lower() for v in card.get("flags", []) + card.get("warnings", [])]
        if not actual_flow or any(
            "annualis" in flag or "annualiz" in flag or "saar" in flag for flag in flags
        ):
            raise ValueError(
                "Sum requires verified, nonannualised quarterly currency flows; choose mean"
            )
    needed = {("M", "Q"): 3, ("Q", "A"): 4, ("M", "A"): 12}[(native, target)]
    grouped = x.groupby(index.asfreq(period_frequency(target)))
    counts = grouped.count()
    result = (
        grouped.mean() if method == "mean" else grouped.sum() if method == "sum" else grouped.last()
    )
    incomplete = counts != needed
    result = result.mask(incomplete)
    detail.update(
        {
            "method": method,
            "required_observations": needed,
            "incomplete_periods": [label(period) for period in period_index(result)[incomplete]],
        }
    )
    return result, detail


def _longest_run(valid: pd.Series[Any]) -> list[pd.Period]:
    best: list[pd.Period] = []
    run: list[pd.Period] = []
    index = period_index(valid)
    for position, okay in enumerate(valid.to_numpy(dtype=bool)):
        period = index[position]
        if okay:
            # Do not treat an externally supplied compressed index as contiguous.
            if run and period.ordinal != run[-1].ordinal + 1:
                run = []
            run.append(period)
            if len(run) >= len(best):
                best = list(run)
        else:
            run = []
    return best


def _stale_check(
    spec: dict[str, Any],
    card: dict[str, Any],
    x: pd.Series[Any],
    start: pd.Period,
    end: pd.Period | None,
    frequency: str,
    country: str,
) -> dict[str, Any] | None:
    flags = set(card.get("flags", [])) | set(card.get("warnings", []))
    if not card.get("stale") and "stale" not in flags:
        return None
    # Check complete converted and transformed observations, not the enclosing
    # quarter of the last raw month: February does not establish Q1 coverage.
    observed = x.notna() & np.isfinite(x)
    restricted = False
    if end is not None and start <= end:
        requested = pd.period_range(start, end, freq=period_frequency(frequency))
        restricted = bool(observed.reindex(requested, fill_value=False).all())
    critical = spec["role"] in {"shock", "response", "dependent"}
    safe_periods = _longest_run(observed)
    fix = None
    if safe_periods:
        fix = {"sample": {"start": label(safe_periods[0]), "end": label(safe_periods[-1])}}
    message = f"{spec['concept_id']} ends at {card.get('last_date', 'an old date')}. "
    message += (
        "Restrict the sample explicitly to complete observed periods before using this role."
        if critical and not restricted
        else "The result uses an old data history."
    )
    return check(
        "block" if critical and not restricted else "warn",
        "stale_input",
        message,
        country=country,
        concept_id=spec["concept_id"],
        explicit_observed_sample=restricted,
        fix=fix,
    )


def prepare_country(
    config: dict[str, Any],
    bundle: dict[str, Any],
    country: str,
) -> tuple[AnalysisData, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    frequency = config["frequency"]
    freq = period_frequency(frequency)
    entry = bundle["countries"][country]
    provenance = {
        "source_data_sha256": input_fingerprint(
            {
                "snapshot_id": bundle.get("snapshot_id"),
                "country": country,
                "metadata": entry["metadata"],
                "series": {
                    spec["concept_id"]: entry["series"].get(spec["concept_id"])
                    for spec in config["series"]
                },
            }
        ),
        "source_data_hash_basis": "Selected original country metadata, series cards "
        "and observations; canonical JSON numbers.",
        "preparation_config": deepcopy(
            {
                key: config[key]
                for key in ("frequency", "sample", "series", "aggregation", "special_periods")
            }
        ),
    }
    frames: dict[str, pd.Series[Any]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    conversions: dict[str, Any] = {}
    transforms: dict[str, Any] = {}
    request_start = pd.Period(config["sample"]["start"], freq=freq)
    start = request_start
    if any(s["role"] == "shock" and s["concept_id"] == "policy_rate" for s in config["series"]):
        adoption = entry["metadata"].get("euro_adoption")
        if (
            adoption
            and config["sample"]["start"]
            == {"M": "1999-01", "Q": "1999-Q1", "A": "1999"}[frequency]
        ):
            adopted = pd.Period(adoption, freq=freq)
            # Do not mix the pre-adoption portion of a quarter/year into an ECB shock.
            if pd.Timestamp(adoption) > adopted.start_time:
                adopted += 1
            start = max(start, adopted)
            if start > request_start:
                checks.append(
                    check(
                        "info",
                        "euro_sample_start",
                        "The default shock sample starts at euro adoption.",
                        country=country,
                        adoption=adoption,
                    )
                )
    end = (
        None
        if config["sample"]["end"] == "latest"
        else pd.Period(config["sample"]["end"], freq=freq)
    )
    for spec in config["series"]:
        cid = spec["concept_id"]
        item = entry["series"].get(cid, {"metadata": {"status": "missing"}, "observations": []})
        card = item["metadata"]
        metadata[cid] = card
        observations = item["observations"]
        if card.get("status") == "missing" or not observations:
            publication = card.get("publication", {})
            excluded = bool(publication.get("excluded_observations"))
            message = (
                f"{cid} in {country} is not included in this publication candidate because "
                "its source data are not cleared for redistribution; choose an included indicator."
                if excluded
                else f"No data for {cid} in {country}; remove it or choose another indicator."
            )
            checks.append(
                check(
                    "block",
                    "missing_coverage",
                    message,
                    country=country,
                    concept_id=cid,
                    fix={"remove_series": cid},
                    **({"publication": publication} if excluded else {}),
                )
            )
            continue
        if card.get("status") == "limited":
            checks.append(
                check(
                    "warn",
                    "limited_coverage",
                    f"{cid} has data limits: " + ", ".join(card.get("reason_codes", [])),
                    country=country,
                    concept_id=cid,
                )
            )
        flags = sorted(set(card.get("flags", [])) | set(card.get("warnings", [])))
        if flags:
            checks.append(
                check(
                    "warn",
                    "source_warning",
                    f"{cid} carries source warnings; inspect its series card.",
                    country=country,
                    concept_id=cid,
                    flags=flags,
                )
            )
        native = card["frequency"]
        index = pd.PeriodIndex([row[0] for row in observations], freq=period_frequency(native))
        if index.has_duplicates:
            raise ValueError("Duplicate observations in snapshot bundle")
        values = np.asarray([float(row[1]) for row in observations])
        if not np.isfinite(values).all():
            raise ValueError("Snapshot observations must be finite; missing periods must be absent")
        x = pd.Series(values, index=index).sort_index()
        native_index = period_index(x)
        x = x.reindex(
            pd.period_range(native_index[0], native_index[-1], freq=period_frequency(native))
        )
        try:
            x, conversion = _convert(x, native, frequency, config["aggregation"].get(cid), card)
            conversions[cid] = conversion
        except ValueError as exc:
            checks.append(
                check("block", "freq_mismatch", str(exc), country=country, concept_id=cid)
            )
            continue
        if end is not None:
            x = x.loc[period_index(x) <= end]
        if spec["transform"] in {"hp_cycle", "hamilton_cycle"}:
            missing_before_start = np.flatnonzero(x.isna().to_numpy() & (period_index(x) < start))
            if len(missing_before_start):
                x = x.iloc[int(missing_before_start[-1]) + 1 :]
        try:
            x, transform = apply_transform(
                x, spec["transform"], frequency, spec.get("transform_params", {})
            )
        except ValueError as exc:
            checks.append(
                check("block", "invalid_transform", str(exc), country=country, concept_id=cid)
            )
            continue
        transforms[cid] = transform
        invalid = [
            p
            for p in transform["invalid_periods"]
            if p >= label(start) and (end is None or p <= label(end))
        ]
        if invalid:
            checks.append(
                check(
                    "block",
                    "invalid_transform",
                    f"{cid} has values outside the transformation domain.",
                    country=country,
                    concept_id=cid,
                    periods=invalid,
                    fix={"transform": "level"},
                )
            )
        if transform.get("retrospective_filter"):
            checks.append(
                check(
                    "warn",
                    "retrospective_filter",
                    "The trend uses the selected historical sample; endpoint estimates can change.",
                    country=country,
                    concept_id=cid,
                )
            )
        stale = _stale_check(spec, card, x, request_start, end, frequency, country)
        if stale:
            checks.append(stale)
        frames[cid] = x
    empty = AnalysisData(pd.DataFrame(), country, frequency, {}, metadata)
    if len(frames) != len(config["series"]):
        empty.sample = {
            **provenance,
            "requested": config["sample"],
            "start": None,
            "end": None,
            "nobs": 0,
            "dropped_periods": [],
            "frequency_conversion": conversions,
            "transforms": transforms,
            "frequency": frequency,
        }
        return empty, checks
    wide = pd.DataFrame(frames)
    requested_end = (
        end if end is not None else max(period_index(series)[-1] for series in frames.values())
    )
    grid = pd.period_range(start, requested_end, freq=freq)
    wide = wide.reindex(grid)
    valid = pd.Series(np.isfinite(wide.to_numpy(dtype=float)).all(axis=1), index=grid)
    reasons: dict[pd.Period, list[str]] = {
        period: [
            column for column in wide.columns if not math_isfinite(wide.iloc[position][column])
        ]
        for position, period in enumerate(grid)
        if not bool(valid.iloc[position])
    }
    covid_window = config["special_periods"].get("covid_window", {})
    covid_start = (
        pd.Period(covid_window["start"], freq=freq).start_time
        if covid_window
        else pd.Timestamp("2020-01-01")
    )
    covid_end = (
        pd.Period(covid_window["end"], freq=freq).end_time
        if covid_window
        else pd.Timestamp("2021-06-30")
    )
    covid = {
        period
        for period in grid
        if period.start_time <= covid_end and period.end_time >= covid_start
    }
    if config["special_periods"]["covid"] == "exclude":
        for position, period in enumerate(grid):
            if period in covid:
                valid.iloc[position] = False
                reasons.setdefault(period, []).append("covid_excluded")
    chosen = _longest_run(valid)
    chosen_set = set(chosen)
    excluded_valid = [
        period
        for position, period in enumerate(grid)
        if valid.iloc[position] and period not in chosen_set
    ]
    if excluded_valid:
        checks.append(
            check(
                "warn",
                "sample_fragmented",
                "Gaps split the common sample. "
                "The longest contiguous window preserves calendar lags.",
                country=country,
                dropped_valid_periods=[label(period) for period in excluded_valid],
            )
        )
        for period in excluded_valid:
            reasons[period] = ["outside_longest_contiguous_window"]
    dropped = [
        {"period": label(period), "reasons": reasons[period]}
        for period in grid
        if period not in chosen_set
    ]
    if dropped:
        checks.append(
            check(
                "warn",
                "common_sample_dropped",
                "Some requested periods are unavailable after "
                "conversion, transformation or restrictions.",
                country=country,
                count=len(dropped),
            )
        )
    if not chosen:
        checks.append(
            check(
                "block",
                "empty_common_sample",
                "No common observed sample remains.",
                country=country,
            )
        )
    selected = wide.reindex(pd.PeriodIndex(chosen, freq=freq)).copy()
    sample = {
        **provenance,
        "requested": config["sample"],
        "effective_requested_start": label(start),
        "start": label(chosen[0]) if chosen else None,
        "end": label(chosen[-1]) if chosen else None,
        "nobs": len(chosen),
        "common_nobs": len(chosen),
        "frequency": frequency,
        "periods": [label(period) for period in chosen],
        "dropped_periods": dropped,
        "frequency_conversion": conversions,
        "transforms": transforms,
        "rule": "longest contiguous complete common sample; "
        "later window wins ties; no interpolation",
    }
    selected.index = pd.Index(sample["periods"], name="period")
    exog = None
    if config["special_periods"]["covid"] == "dummy":
        selected_covid = [period for period in chosen if period in covid]
        if selected_covid:
            exog = pd.DataFrame(
                {
                    f"covid_{label(period)}": [float(other == period) for other in chosen]
                    for period in selected_covid
                },
                index=selected.index,
            )
    return AnalysisData(selected, country, frequency, sample, metadata, exog), checks


def math_isfinite(value: Any) -> bool:
    return bool(np.isfinite(float(value)))
