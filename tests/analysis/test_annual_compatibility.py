"""Annual public frequency A maps to Y only at the pandas boundary."""

from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from macrolab.analysis.config import validated_config
from macrolab.analysis.data import prepare_country
from macrolab.analysis.engine import compatibility, run_analysis
from macrolab.checks.core import _covid_checks
from macrolab.models.base import AnalysisData


def annual_inputs(model, treatment):
    periods = [str(year) for year in range(1999, 2026)]
    config = validated_config(
        {
            "schema_version": 1,
            "snapshot_id": "annual-fixture",
            "countries": ["AAA"] if model == "desc.plot" else ["AAA", "BBB"],
            "frequency": "A",
            "sample": {"start": "1999", "end": "latest"},
            "series": [{"concept_id": "debt", "role": "response", "transform": "level"}],
            "aggregation": {"debt": "mean"},
            "model": {"id": model, "params": {}},
            "special_periods": {
                "covid": treatment,
                "covid_window": {"start": "2020", "end": "2021"},
            },
            "comparison": {"enabled": False},
        }
    )
    bundle = {"snapshot_id": config["snapshot_id"], "countries": {}}
    for i, country in enumerate(config["countries"]):
        values = 50 + i * 10 + np.arange(27) + np.sin(np.arange(27))
        bundle["countries"][country] = {
            "metadata": {"iso3": country},
            "series": {
                "debt": {
                    "metadata": {
                        "concept_id": "debt",
                        "frequency": "A",
                        "status": "available_note",
                        "first_date": "1999",
                        "last_date": "2025",
                        "stale": False,
                        "flags": [],
                        "warnings": [],
                        "unit": "percent_gdp",
                    },
                    "observations": list(zip(periods, values.tolist(), strict=True)),
                }
            },
        }
    return config, bundle


@pytest.mark.parametrize("model", ["desc.plot", "desc.compare"])
@pytest.mark.parametrize("treatment", ["include", "dummy", "exclude"])
def test_normalised_annual_compatibility_execution_and_immutability(model, treatment):
    config, bundle = annual_inputs(model, treatment)
    before = deepcopy((config, bundle))
    selected = next(m for m in compatibility(config, bundle)["models"] if m["id"] == model)
    assert selected["available"], selected["checks"]
    result = run_analysis(config, bundle)
    assert result["status"] == "ok"
    assert result["config"]["frequency"] == "A"
    assert result["config"]["special_periods"] == config["special_periods"]
    expected_n = 21 if treatment == "exclude" else 27
    row = result["results"][0]
    assert row["actual_sample"]["frequency"] == "A"
    assert row["actual_sample"]["nobs"] == expected_n
    assert row["actual_sample"]["start"] == "1999"
    assert row["actual_sample"]["end"] == ("2019" if treatment == "exclude" else "2025")
    if model == "desc.plot":
        expected = bundle["countries"]["AAA"]["series"]["debt"]["observations"][:expected_n]
        assert [(r["date"], r["value"]) for r in row["filtered_series"]] == expected
    else:
        for comparison in row["test_results"]:
            country = comparison["country"]
            expected = bundle["countries"][country]["series"]["debt"]["observations"][:expected_n]
            assert comparison["nobs"] == expected_n
            assert comparison["statistic"] == np.mean([v for _, v in expected])
        assert sorted(r["rank"] for r in row["test_results"]) == [1, 2]
    for country in config["countries"]:
        data, _ = prepare_country(config, bundle, country)
        findings = _covid_checks(data, config)
        assert len(findings) == 1
        finding = findings[0]
        assert finding["code"] == "covid_period"
        assert finding["level"] == ("warn" if treatment == "include" else "info")
        assert finding["periods"] == ["2020", "2021"]
        assert finding["treatment"] == treatment
        if treatment == "dummy":
            assert finding["applied"] is False
        if treatment == "exclude":
            dropped = {r["period"]: r["reasons"] for r in data.sample["dropped_periods"]}
            assert all("covid_excluded" in dropped[p] for p in ["2020", "2021"])
    assert (config, bundle) == before


@pytest.mark.parametrize(
    "frequency,start,end,window,expected",
    [
        (
            "M",
            "2019-01",
            "2022-12",
            {"start": "2020-03", "end": "2021-02"},
            [str(p) for p in pd.period_range("2020-03", "2021-02", freq="M")],
        ),
        (
            "Q",
            "2019Q1",
            "2022Q4",
            {"start": "2020-Q2", "end": "2021-Q1"},
            ["2020-Q2", "2020-Q3", "2020-Q4", "2021-Q1"],
        ),
        ("A", "2019", "2022", {"start": "2020", "end": "2021"}, ["2020", "2021"]),
    ],
)
@pytest.mark.parametrize("treatment", ["include", "dummy", "exclude"])
def test_explicit_covid_window_boundaries_and_existing_findings(
    frequency, start, end, window, expected, treatment
):
    periods = pd.period_range(start, end, freq="Y" if frequency == "A" else frequency)
    labels = [str(p).replace("Q", "-Q") for p in periods]
    frame = pd.DataFrame({"x": np.arange(len(periods))}, index=labels)
    dropped = []
    if treatment == "exclude":
        frame = frame.drop(expected)
        dropped = [{"period": p, "reasons": ["covid_excluded"]} for p in expected]
    data = AnalysisData(frame, frequency=frequency, sample={"dropped_periods": dropped})
    config = {
        "model": {"id": "desc.plot", "params": {}},
        "special_periods": {"covid": treatment, "covid_window": window},
    }
    before = deepcopy(config)
    result = _covid_checks(data, config)[0]
    assert result["periods"] == expected
    assert result["level"] == ("warn" if treatment == "include" else "info")
    assert result["treatment"] == treatment
    if treatment == "include":
        assert (
            result["message"]
            == "COVID periods can dominate estimates; choose include, period dummies or exclude."
        )
        assert result["fix"] == {"special_periods": {"covid": "dummy"}}
    elif treatment == "dummy":
        assert (
            result["message"]
            == "COVID periods remain visible. This descriptive, test or filter model "
            "does not use the requested regression dummies."
        )
        assert result["applied"] is False
    else:
        assert (
            result["message"]
            == "COVID periods were excluded; calendar gaps are not treated as "
            "consecutive observations."
        )
    assert config == before
