import json
import socket
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from macrolab import smoke
from macrolab.smoke import (
    ObservationError,
    build_smoke_summary,
    canonical_json,
    generate_observations,
    summarize_observations,
    validate_observations,
)


def test_seed_reproduces_data_config_summary_and_actual_samples() -> None:
    first = build_smoke_summary(seed=12)
    second = build_smoke_summary(seed=12)
    assert first == second
    assert first["actual_sample"] == {"start": "1999-Q1", "end": "2018-Q4", "frequency": "Q"}
    assert first["counts"]["observations"] == 480
    assert all(summary["observations"] == 80 for summary in first["series_summaries"])
    assert all(
        summary["actual_sample"] == {"start": "1999-Q1", "end": "2018-Q4"}
        for summary in first["series_summaries"]
    )
    changed = build_smoke_summary(seed=13)
    assert first["config_hash"] != changed["config_hash"]
    assert first["observations_hash"] != changed["observations_hash"]
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_quick_runs_offline_and_saves_only_inside_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def reject_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("The G0 quick check must never access the network.")

    monkeypatch.setattr(socket, "socket", reject_network)
    monkeypatch.setattr(smoke, "project_root", lambda: tmp_path)
    result = smoke.run_quick(seed=7)
    output = tmp_path / "runs" / "quick" / "summary.json"
    assert json.loads(output.read_text()) == result
    assert result["synthetic"] is True
    assert result["elapsed_seconds"] < 120
    assert list(tmp_path.rglob("*.json")) == [output]


def test_duplicate_observations_are_rejected() -> None:
    observations = generate_observations(periods=2)
    with pytest.raises(ObservationError, match="duplicate observation"):
        validate_observations(observations + (observations[0],))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "oops"])
def test_nonfinite_and_nonnumeric_observations_are_rejected(value: Any) -> None:
    observations = generate_observations(periods=2)
    wrong = replace(observations[0], value=value)
    with pytest.raises(ObservationError, match="finite number"):
        validate_observations((wrong,) + observations[1:])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("country", "DEU", "fictional"),
        ("concept_id", "unknown", "unknown synthetic concept"),
        ("date", "1999-Q5", "invalid quarterly date"),
        ("frequency", "M", "quarterly, explicitly synthetic"),
        ("source", "OECD", "quarterly, explicitly synthetic"),
        ("unit", "percent", "incorrect unit"),
        ("value", -1.0, "must be positive"),
    ],
)
def test_wrong_observation_metadata_is_rejected(field: str, value: Any, message: str) -> None:
    observations = generate_observations(periods=2)
    wrong = replace(observations[0], **{field: value})
    with pytest.raises(ObservationError, match=message):
        validate_observations((wrong,) + observations[1:])


def test_missing_quarter_is_reported_without_interpolation() -> None:
    observations = generate_observations(periods=2)
    with pytest.raises(ObservationError, match=r"missing=\['1999-Q1'\]"):
        summarize_observations(observations[1:], start="1999-Q1", periods=2)


@pytest.mark.parametrize("periods", [0, -1, 121, True, 1.5])
def test_invalid_fixture_periods_are_rejected(periods: Any) -> None:
    with pytest.raises(ValueError, match="periods must be an integer"):
        generate_observations(periods=periods)
