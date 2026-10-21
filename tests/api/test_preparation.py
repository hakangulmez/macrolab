"""Unvalidated or altered source observations must not enter the browser manifest."""

from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

PREPARE = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/g3_prepare.py"))[
    "prepare"
]


def test_unvalidated_snapshot_cannot_prepare_browser_files(tmp_path: Path) -> None:
    directory = tmp_path / "data/processed/current"
    directory.mkdir(parents=True)
    (directory / "processed_manifest.json").write_text(json.dumps({"validation_passed": False}))
    with pytest.raises(ValueError, match="validated accepted"):
        PREPARE(tmp_path)
    assert not (tmp_path / "web/public").exists()


def test_altered_country_bytes_cannot_prepare_a_manifest(tmp_path: Path) -> None:
    directory = tmp_path / "data/processed/current"
    (directory / "browser").mkdir(parents=True)
    payload = b'{"country":{"iso3":"USA"},"value":123}'
    (directory / "browser/USA.json").write_bytes(payload)
    (directory / "processed_manifest.json").write_text(
        json.dumps(
            {
                "validation_passed": True,
                "snapshot_id": "fixture",
                "countries": 1,
                "files": {
                    "browser/USA.json": {
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload) + 1,
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="checksum differs"):
        PREPARE(tmp_path)
    assert not (tmp_path / "web/public/data/manifest.json").exists()
