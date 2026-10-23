import copy
import json
from pathlib import Path

import pytest
from jsonschema import validate

from macrolab.analysis.config import (
    ConfigError,
    config_hash,
    decode_config,
    encode_config,
    validated_config,
)
from macrolab.models.registry import PLUGINS, catalogue

ROOT = Path(__file__).resolve().parents[2]


def template():
    return json.loads((ROOT / "configs/templates/monetary_policy.json").read_text())


def test_config_roundtrip_schema_and_hash():
    config = validated_config(template())
    assert decode_config(encode_config(config)) == config
    assert config_hash(config) == config_hash(dict(reversed(list(config.items()))))
    validate(config, json.loads((ROOT / "schemas/analysis_config.schema.json").read_text()))
    changed = copy.deepcopy(config)
    changed["seed"] += 1
    assert config_hash(changed) != config_hash(config)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["countries"].append(c["countries"][0]),
        lambda c: c["model"].update(id="var.bvar"),
        lambda c: c["model"]["params"].update(lags=True),
        lambda c: c["model"]["params"].update(lags=100),
        lambda c: c["model"]["params"].update(unknown=1),
        lambda c: c["series"].append(c["series"][0]),
        lambda c: c["identification"]["params"].update(order=["cpi"]),
        lambda c: c["identification"]["params"].update(order=[{}]),
        lambda c: c["outputs"]["irf"].update(shock_size=float("nan")),
        lambda c: c.update(seed=-1),
    ],
)
def test_invalid_requests_are_rejected(mutation):
    config = template()
    mutation(config)
    with pytest.raises(ConfigError):
        validated_config(config)


@pytest.mark.parametrize("token", ["x", "v1.!!!", "v1." + "a" * 100001])
def test_invalid_share_payload(token):
    with pytest.raises(ConfigError):
        decode_config(token)


def test_release_registry_complete_and_explicit():
    assert len(PLUGINS) == 16
    for plugin in catalogue():
        assert all(
            plugin[k] for k in ["id", "family", "title", "summary", "assumptions", "references"]
        )
        assert plugin["runtime"] == "browser"
