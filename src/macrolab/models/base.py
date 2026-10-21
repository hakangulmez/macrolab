"""Shared pure-Python model contract used by native and WebAssembly runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import pandas as pd

AnalysisConfig = dict[str, Any]
ModelResult = dict[str, Any]
CheckLevel = Literal["ok", "info", "warn", "block"]
CheckPhase = Literal["preflight", "pre_estimation", "post_estimation"]


def check(
    level: CheckLevel,
    code: str,
    message: str,
    *,
    phase: CheckPhase = "pre_estimation",
    **context: Any,
) -> dict[str, Any]:
    """Serializable check, with an optional suggested config change in context.fix."""
    return {
        "level": level,
        "code": code,
        "message": message,
        "phase": phase,
        "fix": context.pop("fix", None),
        **context,
    }


def sample_size_check(
    nobs: int,
    count: int,
    *,
    minimum_observations: int = 0,
    phase: CheckPhase = "pre_estimation",
    **context: Any,
) -> dict[str, Any] | None:
    """Separate estimability requirements from the requested precision heuristic.

    A low observations/parameter ratio alone never blocks a fit. Nonpositive
    residual degrees of freedom and each model's absolute minimum still block.
    """
    level: CheckLevel
    if nobs < minimum_observations or nobs <= count:
        level = "block"
        message = (
            f"At least {minimum_observations} effective observations are required."
            if nobs < minimum_observations
            else "Positive residual degrees of freedom are required."
        )
    elif nobs < 5 * count:
        level = "warn"
        message = "Fewer than five observations per parameter; estimates may be imprecise."
    elif nobs < 10 * count:
        level = "info"
        message = (
            "Five to fewer than ten observations per parameter; interpret precision cautiously."
        )
    else:
        return None
    return check(
        level,
        "small_sample",
        message,
        phase=phase,
        nobs=nobs,
        parameters=count,
        observations_per_parameter=nobs / count if count else None,
        minimum_observations=minimum_observations,
        **context,
    )


@dataclass
class AnalysisData:
    """One country's regular common sample; separate panels support comparison only."""

    frame: pd.DataFrame
    country: str = "SYN"
    frequency: str = "Q"
    sample: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    exog: pd.DataFrame | None = None
    panels: dict[str, pd.DataFrame] = field(default_factory=dict)


class ModelPlugin(Protocol):
    id: str
    family: str
    title: str
    summary: str
    assumptions: list[str]
    label: str
    runtime: str
    inputs: dict[str, Any]
    params: dict[str, Any]
    references: list[dict[str, str]]

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]: ...
    def run(self, data: AnalysisData, config: AnalysisConfig) -> ModelResult: ...
    def to_script(self, config: AnalysisConfig) -> str: ...


class BasePlugin:
    id = ""
    family = ""
    title = ""
    summary = ""
    assumptions: list[str] = []
    label = "Descriptive"
    runtime = "browser"
    inputs: dict[str, Any] = {}
    params: dict[str, Any] = {}
    references: list[dict[str, str]] = []

    def check(self, data: AnalysisData, config: AnalysisConfig) -> list[dict[str, Any]]:
        return []

    def run(self, data: AnalysisData, config: AnalysisConfig) -> ModelResult:
        raise NotImplementedError

    def to_script(self, config: AnalysisConfig) -> str:
        from macrolab.export.script import config_script

        return config_script(config)


def roles(config: AnalysisConfig, *wanted: str) -> list[str]:
    return [s["concept_id"] for s in config["series"] if s["role"] in wanted]


def parameters(config: AnalysisConfig) -> dict[str, Any]:
    return dict(config.get("model", {}).get("params", {}))
