"""Offline review seeding verifies inputs and never replaces different bytes."""

import base64
import hashlib
import json
import runpy
from pathlib import Path

import pytest

SEED = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/seed_review_inputs.py"))[
    "seed"
]


def inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    source, target = tmp_path / "source", tmp_path / "clone"
    data = source / "data/processed/current"
    (data / "browser").mkdir(parents=True)
    (target / "web/runtime").mkdir(parents=True)
    (target / "configs/templates").mkdir(parents=True)
    (target / "configs/templates/monetary.json").write_text('{"snapshot_id":"fixture"}')
    country = b'{"country":{"iso3":"USA"},"publication_approved":false}'
    (data / "browser/USA.json").write_bytes(country)
    (data / "processed_manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": "fixture",
                "validation_passed": True,
                "files": {
                    "browser/USA.json": {
                        "sha256": hashlib.sha256(country).hexdigest(),
                        "bytes": len(country),
                    }
                },
            }
        )
    )
    accepted = tmp_path / "accepted-evidence.json"
    accepted.write_text(
        json.dumps(
            {
                "snapshot_id": "fixture",
                "processed_manifest_sha256": hashlib.sha256(
                    (data / "processed_manifest.json").read_bytes()
                ).hexdigest(),
            }
        )
    )
    monkeypatch.setitem(SEED.__globals__, "ACCEPTED_EVIDENCE", accepted)
    archive, package = b"npm fixture", b"scientific fixture"
    lock = {
        "pyodide_version": "fixture",
        "runtime_npm_integrity": "sha512-"
        + base64.b64encode(hashlib.sha512(archive).digest()).decode(),
        "packages": {
            "fixture": {
                "file_name": "fixture.whl",
                "bytes": len(package),
                "sha256": hashlib.sha256(package).hexdigest(),
            }
        },
    }
    (target / "web/runtime/assets.lock.json").write_text(json.dumps(lock))
    for name, content in [
        (".cache/pyodide-discovery/pyodide-fixture.tgz", archive),
        (".cache/pyodide/fixture/fixture.whl", package),
    ]:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return source, target


def test_seed_is_complete_idempotent_and_uses_clone_local_snapshot_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = inputs(tmp_path, monkeypatch)
    first = SEED(source, target)
    assert first == SEED(source, target)
    current = target / "data/processed/current"
    assert current.is_symlink() and current.readlink() == Path("snapshots/fixture")
    assert current.resolve().is_relative_to(target)
    assert len(first["files"]) == 4 and first["network_requests"] == 0
    assert not (target / "web/public").exists()


def test_tampered_inputs_fail_before_any_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = inputs(tmp_path, monkeypatch)
    (source / ".cache/pyodide/fixture/fixture.whl").write_bytes(b"different")
    with pytest.raises(ValueError, match="asset mismatch"):
        SEED(source, target)
    assert not (target / "data").exists()


def test_different_destination_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = inputs(tmp_path, monkeypatch)
    path = target / ".cache/pyodide/fixture/fixture.whl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"existing data")
    with pytest.raises(ValueError, match="Refusing to replace"):
        SEED(source, target)
    assert path.read_bytes() == b"existing data"
    assert not (target / "data").exists()


def test_self_consistent_changed_snapshot_cannot_replace_accepted_vintage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = inputs(tmp_path, monkeypatch)
    data = source / "data/processed/current"
    country = b'{"country":{"iso3":"USA"},"publication_approved":false,"value":999}'
    (data / "browser/USA.json").write_bytes(country)
    manifest_path = data / "processed_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["browser/USA.json"] = {
        "sha256": hashlib.sha256(country).hexdigest(),
        "bytes": len(country),
    }
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="committed accepted G1.1 evidence"):
        SEED(source, target)
    assert not (target / "data").exists()


def test_manifest_symlink_cannot_escape_authorised_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = inputs(tmp_path, monkeypatch)
    manifest_path = source / "data/processed/current/processed_manifest.json"
    outside = tmp_path / "outside-manifest.json"
    manifest_path.rename(outside)
    manifest_path.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes its checkout"):
        SEED(source, target)
    assert not (target / "data").exists()
