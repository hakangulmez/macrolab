"""Explicit validated v0 model registry shared by both runtimes."""

from __future__ import annotations

from typing import Any

from macrolab.compare.common_shock import CommonShockPlugin
from macrolab.ident.external_series import ExternalSeriesPlugin
from macrolab.models.base import ModelPlugin
from macrolab.models.linear import PLUGINS as LINEAR
from macrolab.models.lp import LPPlugin
from macrolab.models.var import PLUGINS as VAR
from macrolab.outputs.hd import HistoricalDecompositionPlugin

PLUGINS: dict[str, ModelPlugin] = {
    plugin.id: plugin
    for plugin in [
        *LINEAR,
        *VAR,
        LPPlugin(),
        HistoricalDecompositionPlugin(),
        ExternalSeriesPlugin(),
        CommonShockPlugin(),
    ]
}


def get_plugin(model_id: str) -> ModelPlugin:
    if model_id not in PLUGINS:
        raise ValueError(f"Unreleased model: {model_id}")
    return PLUGINS[model_id]


def catalogue() -> list[dict[str, Any]]:
    return [
        {
            name: getattr(plugin, name)
            for name in (
                "id",
                "family",
                "title",
                "summary",
                "assumptions",
                "label",
                "runtime",
                "inputs",
                "params",
                "references",
            )
        }
        for plugin in PLUGINS.values()
    ]
