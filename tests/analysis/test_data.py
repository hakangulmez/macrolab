"""Calendar, coverage and transform guards using entirely synthetic JSON bundles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pandas as pd
import pytest

from macrolab.analysis.data import _convert, prepare_country, snapshot_bundle
from macrolab.analysis.transforms import apply_transform, invert_transform, period_frequency


def bundle(
    periods: list[str], values: list[float], native: str = "Q", **metadata: Any
) -> dict[str, Any]:
    card = {
        "concept_id": "y",
        "frequency": native,
        "status": "available",
        "first_date": periods[0],
        "last_date": periods[-1],
        "flags": [],
        "warnings": [],
        **metadata,
    }
    return {
        "snapshot_id": "synthetic",
        "countries": {
            "SYN": {
                "metadata": {"iso3": "SYN"},
                "series": {
                    "y": {"metadata": card, "observations": list(zip(periods, values, strict=True))}
                },
            }
        },
    }


def config(
    start: str = "2020-Q1",
    end: str = "latest",
    frequency: str = "Q",
    transform: str = "level",
    role: str = "dependent",
    **params: Any,
) -> dict[str, Any]:
    return {
        "frequency": frequency,
        "sample": {"start": start, "end": end},
        "aggregation": {"y": "mean"},
        "special_periods": {"covid": "include"},
        "series": [
            {"concept_id": "y", "role": role, "transform": transform, "transform_params": params}
        ],
    }


def test_monthly_quarterly_means_never_use_partial_periods() -> None:
    source = bundle([f"2020-{month:02d}" for month in range(1, 6)], [1, 2, 3, 4, 5], "M")
    data, checks = prepare_country(config(), source, "SYN")
    assert data.frame.y.tolist() == [2.0]
    assert data.sample["periods"] == ["2020-Q1"]
    assert data.sample["frequency_conversion"]["y"]["incomplete_periods"] == ["2020-Q2"]
    assert data.sample["dropped_periods"] == [{"period": "2020-Q2", "reasons": ["y"]}]
    assert not any(c["level"] == "block" for c in checks)


def test_quarterly_annual_means_require_all_four_quarters() -> None:
    periods = [str(p) for p in pd.period_range("2019Q1", periods=7, freq="Q")]
    data, _ = prepare_country(
        config("2019", frequency="A"), bundle(periods, list(range(1, 8))), "SYN"
    )
    assert data.frame.y.tolist() == [2.5]
    assert data.sample["periods"] == ["2019"]
    assert data.sample["frequency_conversion"]["y"]["incomplete_periods"] == ["2020"]


@pytest.mark.parametrize("kind", ["upsampling", "missing_rule"])
def test_frequency_conversion_requires_authorised_direction_and_rule(kind: str) -> None:
    cfg = config("2020-01", frequency="M") if kind == "upsampling" else config()
    source = (
        bundle(["2020Q1", "2020Q2"], [1, 2])
        if kind == "upsampling"
        else bundle(["2020-01", "2020-02", "2020-03"], [1, 2, 3], "M")
    )
    cfg["aggregation"] = {}
    data, checks = prepare_country(cfg, source, "SYN")
    assert data.frame.empty
    assert any(c["level"] == "block" and c["code"] == "freq_mismatch" for c in checks)


def test_sum_requires_verified_currency_flow_and_last_requires_stock_metadata() -> None:
    values = pd.Series([1.0, 2, 3, 4], index=pd.period_range("2020Q1", periods=4, freq="Q"))
    card = {
        "verified_period_flow": True,
        "source_segments": [{"unit": "XDC"}],
        "aggregation_rules": {"quarterly_to_annual": {"conditional_sum_allowed": True}},
    }
    summed, _ = _convert(values, "Q", "A", "sum", card)
    assert summed.iloc[0] == 10
    for changes in (
        {"verified_period_flow": False},
        {"source_segments": [{"unit": "IX"}]},
        {"flags": ["annualised_SAAR"]},
    ):
        with pytest.raises(ValueError, match="currency flows"):
            _convert(values, "Q", "A", "sum", card | changes)
    with pytest.raises(ValueError, match="stock"):
        _convert(values, "Q", "A", "last", {})
    stock = {"aggregation_rules": {"quarterly_to_annual": {"optional": ["last"]}}}
    last, _ = _convert(values, "Q", "A", "last", stock)
    assert last.iloc[0] == 4
    partial, _ = _convert(values.iloc[:3], "Q", "A", "last", stock)
    assert pd.isna(partial.iloc[0])


def test_gaps_do_not_compress_lags_and_longest_run_ties_choose_later() -> None:
    source = bundle(["2020Q1", "2020Q2", "2020Q4", "2021Q1"], [10, 12, 20, 23])
    data, checks = prepare_country(config(), source, "SYN")
    assert data.sample["periods"] == ["2020-Q4", "2021-Q1"]
    assert any(c["code"] == "sample_fragmented" for c in checks)
    dropped = {r["period"]: r["reasons"] for r in data.sample["dropped_periods"]}
    assert dropped["2020-Q3"] == ["y"]
    assert dropped["2020-Q2"] == ["outside_longest_contiguous_window"]
    differenced, _ = prepare_country(config(transform="diff"), source, "SYN")
    assert differenced.sample["periods"] == ["2021-Q1"]
    assert differenced.frame.y.tolist() == [3.0]


@pytest.mark.parametrize("role", ["dependent", "shock", "response"])
def test_stale_critical_series_needs_wholly_observed_explicit_sample(role: str) -> None:
    periods = [str(p) for p in pd.period_range("2019-01", "2020-02", freq="M")]
    source = bundle(
        periods,
        [float(i + 1) for i in range(len(periods))],
        "M",
        stale=True,
        status="limited",
        flags=["stale", "definition_warning"],
    )
    for end in ("latest", "2020-Q1"):
        _, checks = prepare_country(config("2019-Q1", end, role=role), source, "SYN")
        assert any(c["code"] == "stale_input" and c["level"] == "block" for c in checks)
    data, checks = prepare_country(config("2019-Q1", "2019-Q4", role=role), source, "SYN")
    assert data.sample["nobs"] == 4
    stale = next(c for c in checks if c["code"] == "stale_input")
    assert stale["level"] == "warn" and stale["explicit_observed_sample"]
    assert any(c["code"] == "limited_coverage" for c in checks)
    assert next(c for c in checks if c["code"] == "source_warning")["flags"] == [
        "definition_warning",
        "stale",
    ]
    assert data.metadata["y"]["flags"] == ["stale", "definition_warning"]


def test_internal_gap_prevents_claiming_wholly_observed_stale_sample() -> None:
    source = bundle(["2019Q1", "2019Q3", "2019Q4"], [1, 3, 4], stale=True)
    _, checks = prepare_country(config("2019-Q1", "2019-Q4"), source, "SYN")
    assert next(c for c in checks if c["code"] == "stale_input")["level"] == "block"


@pytest.mark.parametrize("frequency", ["M", "Q", "A"])
@pytest.mark.parametrize(
    "transform", ["level", "log", "diff", "log_diff", "yoy_pct", "yoy_diff", "index_to_base"]
)
def test_transform_inversion_identity(frequency: str, transform: str) -> None:
    values = 100 * np.exp(np.linspace(0, 0.8, 32))
    index = pd.period_range("1999", periods=len(values), freq=period_frequency(frequency))
    source = pd.Series(values, index=index)
    transformed, metadata = apply_transform(
        source, transform, frequency, {"base_period": str(index[2])}
    )
    valid = transformed.dropna()
    lag = (
        {"M": 12, "Q": 4, "A": 1}[frequency]
        if transform.startswith("yoy")
        else 1
        if transform in {"diff", "log_diff"}
        else 0
    )
    restored = invert_transform(
        valid.tolist(), transform, values[:lag].tolist(), frequency, metadata.get("base_value")
    )
    np.testing.assert_allclose(restored, values[lag:], rtol=1e-12, atol=1e-10)


def test_qoq_saar_inverse_and_frequency_domain() -> None:
    values = pd.Series([100.0, 101, 98, 104], index=pd.period_range("2000Q1", periods=4, freq="Q"))
    result, _ = apply_transform(values, "qoq_saar", "Q")
    np.testing.assert_allclose(
        invert_transform(result.dropna().tolist(), "qoq_saar", [100]), values.iloc[1:]
    )
    with pytest.raises(ValueError, match="quarterly"):
        apply_transform(values, "qoq_saar", "M")
    with pytest.raises(ValueError, match="valid growth"):
        invert_transform([-101], "qoq_saar", [100])


def test_invalid_transform_is_not_mislabelled_frequency_conversion_error() -> None:
    source = bundle(["2020-01", "2020-02", "2020-03"], [-1, -2, -3], "M")
    _, checks = prepare_country(config(transform="hp_cycle", log=True), source, "SYN")
    assert any(c["code"] == "invalid_transform" and c["level"] == "block" for c in checks)
    assert not any(c["code"] == "freq_mismatch" for c in checks)


def test_log_difference_flags_invalid_lag_outside_requested_sample() -> None:
    source = bundle(["2019Q4", "2020Q1", "2020Q2"], [-1, 2, 4])
    _, checks = prepare_country(config(transform="log_diff"), source, "SYN")
    invalid = next(c for c in checks if c["code"] == "invalid_transform")
    assert invalid["periods"] == ["2020-Q1"]


@pytest.mark.parametrize("transform", ["hp_cycle", "hamilton_cycle"])
def test_retrospective_filter_uses_no_values_after_explicit_end(transform: str) -> None:
    periods = [str(p) for p in pd.period_range("1990Q1", periods=100, freq="Q")]
    values = (
        100 * np.exp(np.linspace(0, 1, 100) + np.random.default_rng(511).normal(0, 0.01, 100))
    ).tolist()
    source = bundle(periods, values)
    cfg = config("1999-Q1", "2009-Q4", transform=transform, log=True)
    first, _ = prepare_country(cfg, source, "SYN")
    changed = deepcopy(source)
    for row in range(80, 100):
        changed["countries"]["SYN"]["series"]["y"]["observations"][row] = (
            periods[row],
            values[row] * 100,
        )
    second, _ = prepare_country(cfg, changed, "SYN")
    pd.testing.assert_frame_equal(first.frame, second.frame)
    assert first.sample["transforms"]["y"]["input_end"] == "2009-Q4"


def test_covid_exclusion_keeps_calendar_continuity_and_dummy_alignment() -> None:
    periods = [str(p) for p in pd.period_range("2018Q1", "2023Q4", freq="Q")]
    source = bundle(periods, list(range(1, 25)))
    cfg = config("2018-Q1")
    cfg["special_periods"]["covid"] = "exclude"
    data, _ = prepare_country(cfg, source, "SYN")
    assert data.sample["periods"] == [
        str(p).replace("Q", "-Q") for p in pd.period_range("2021Q3", "2023Q4", freq="Q")
    ]
    cfg["special_periods"]["covid"] = "dummy"
    data, _ = prepare_country(cfg, source, "SYN")
    assert data.exog is not None and data.exog.index.equals(data.frame.index)
    assert data.exog.shape == (24, 6)
    assert data.exog.sum().tolist() == [1.0] * 6


def test_snapshot_loader_rejects_path_traversal_before_filesystem_read() -> None:
    with pytest.raises(ValueError, match="snapshot ID"):
        snapshot_bundle("../../outside", ["SYN"], ["y"])
    with pytest.raises(ValueError, match="country"):
        snapshot_bundle("valid", ["../../outside"], ["y"])


@pytest.mark.parametrize("transform", ["hp_cycle", "hamilton_cycle"])
def test_logged_filter_reconstructs_levels_from_its_recorded_trend(transform: str) -> None:
    values = 100 * np.exp(np.linspace(0, 0.5, 80) + np.random.default_rng(190).normal(0, 0.02, 80))
    original = pd.Series(values, index=pd.period_range("1990Q1", periods=80, freq="Q"))
    cycle, metadata = apply_transform(original, transform, "Q", {"log": True})
    trend = np.asarray([np.nan if value is None else value for value in metadata["trend"]])
    valid = cycle.notna().to_numpy()
    recovered = np.exp(trend[valid] + cycle.to_numpy()[valid] / 100)
    np.testing.assert_allclose(recovered, values[valid], atol=1e-10)
    with pytest.raises(ValueError, match="lossy"):
        invert_transform(cycle.dropna().tolist(), transform, [])


def test_source_input_hash_is_exact_and_stable_across_json_numeric_transport() -> None:
    source = bundle(["2020Q1", "2020Q2", "2020Q3"], [1.0, 2.5, 3.0])
    first, _ = prepare_country(config(), source, "SYN")
    transported = deepcopy(source)
    transported["countries"]["SYN"]["series"]["y"]["observations"] = [
        ["2020Q1", 1],
        ["2020Q2", 2.5],
        ["2020Q3", 3],
    ]
    second, _ = prepare_country(config(), transported, "SYN")
    assert first.sample["source_data_sha256"] == second.sample["source_data_sha256"]
    transported["countries"]["SYN"]["series"]["y"]["observations"][1][1] += 1e-12
    changed, _ = prepare_country(config(), transported, "SYN")
    assert first.sample["source_data_sha256"] != changed.sample["source_data_sha256"]
    assert first.sample["preparation_config"]["frequency"] == "Q"
    assert first.sample["preparation_config"]["series"][0]["transform"] == "level"
