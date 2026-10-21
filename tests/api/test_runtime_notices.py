"""Pinned runtime notices are copied locally and fail closed on drift or path escape."""

import hashlib
import json
import runpy
from pathlib import Path

import pytest

COPY = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/runtime_notices.py"))[
    "copy_runtime_notices"
]


def notice_fixture(root: Path) -> Path:
    directory = root / "third_party/runtime"
    directory.mkdir(parents=True)
    text = b"Fixture full notice\n"
    (directory / "LICENSE").write_bytes(text)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pyodide_version": "fixture",
                "python_version": "3.fixture",
                "runtime_npm_integrity": "sha512-fixture",
                "components": [],
                "scope": "fixture",
                "files": [
                    {
                        "path": "LICENSE",
                        "bytes": len(text),
                        "sha256": hashlib.sha256(text).hexdigest(),
                    }
                ],
            }
        )
    )
    (root / "web/runtime").mkdir(parents=True)
    (root / "web/runtime/assets.lock.json").write_text(
        json.dumps(
            {
                "pyodide_version": "fixture",
                "runtime_info": {"python": "3.fixture"},
                "runtime_npm_integrity": "sha512-fixture",
            }
        )
    )
    return directory


def test_notice_bytes_and_manifest_are_retained(tmp_path: Path) -> None:
    directory = notice_fixture(tmp_path)
    result = COPY(tmp_path, tmp_path / "output")
    assert len(result["files"]) == 2
    assert result["publication_approved"] is False
    assert result["unresolved"] == []
    assert (tmp_path / "output/licences/runtime/LICENSE").read_bytes() == (
        directory / "LICENSE"
    ).read_bytes()


def test_tampered_notice_and_runtime_drift_block(tmp_path: Path) -> None:
    directory = notice_fixture(tmp_path)
    (directory / "LICENSE").write_bytes(b"altered")
    with pytest.raises(ValueError, match="checksum"):
        COPY(tmp_path, tmp_path / "output")
    lock = tmp_path / "web/runtime/assets.lock.json"
    value = json.loads(lock.read_text())
    value["runtime_info"]["python"] = "wrong"
    lock.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="versions"):
        COPY(tmp_path, tmp_path / "output")


def test_notice_symlink_escape_blocks(tmp_path: Path) -> None:
    directory = notice_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.write_bytes((directory / "LICENSE").read_bytes())
    (directory / "LICENSE").unlink()
    (directory / "LICENSE").symlink_to(outside)
    with pytest.raises(ValueError, match="contained"):
        COPY(tmp_path, tmp_path / "output")
