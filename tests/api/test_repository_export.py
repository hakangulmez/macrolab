"""A selective source export never imports private history, notes or result files."""

import json
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

EXPORT = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/p2_export_repo.py"))


def fixture(root: Path) -> None:
    files = {
        "README.md": "Private review links",
        "LICENSE": "Fixture licence",
        "DATA.md": "Fixture data policy; [old review](docs/G2_VERIFICATION.json)",
        "docs/SOURCES.md": "Fixture source mappings",
        "docs/models/README.md": "Fixture models",
        "docs/P1_SOFTWARE_NOTICES.md": "Fixture notices",
        "third_party/runtime/SOURCE_AVAILABILITY.md": "Fixture source availability",
        "src/example.py": "ANSWER = 42\n",
        "configs/country_notes.yaml": yaml.safe_dump(
            {
                "notes": [{"text": "Private draft narrative"}],
                "euro_adoptions": {"AUT": {"date": "1999-01-01", "source": "ecb"}},
                "sources": {"ecb": {"url": "https://www.ecb.europa.eu/"}},
            }
        ),
        "docs/G2_VERIFICATION.json": json.dumps({"trend": [1, 2, 3]}),
        "docs/screenshots/review.png": "not copied",
        "docs/COUNTRY_NOTES_REVIEW.md": "Private narrative",
    }
    for name, value in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)
    for args in [
        ["init", "--initial-branch=main"],
        ["add", "--all"],
        [
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Private original history",
        ],
    ]:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_export_omits_private_material_and_makes_exactly_one_new_commit(tmp_path: Path) -> None:
    fixture(tmp_path)
    plan, _ = EXPORT["plan"](tmp_path)
    report = EXPORT["create"](tmp_path, plan["selected_source_sha256"])
    target = tmp_path / "runs/p2/sanitised-repo"
    notes = yaml.safe_load((target / "configs/country_notes.yaml").read_text())
    assert notes["notes"] == []
    assert notes["euro_adoptions"]["AUT"]["date"] == "1999-01-01"
    assert not (target / "docs/G2_VERIFICATION.json").exists()
    assert not (target / "docs/screenshots/review.png").exists()
    assert "Private review links" not in (target / "README.md").read_text()
    assert "local review record omitted" in (target / "DATA.md").read_text()
    assert report["broken_local_markdown_links"] == []
    assert report["commit_count"] == 1
    assert (
        report["author"]
        == report["committer"]
        == {"name": "Hakan Zeki Gülmez", "email": "hakanzekigulmez@gmail.com"}
    )
    assert report["remotes"] == [] and report["copied_original_git"] is False
    with pytest.raises(ValueError, match="already exists"):
        EXPORT["create"](tmp_path, plan["selected_source_sha256"])


def test_source_drift_blocks_before_creating_destination(tmp_path: Path) -> None:
    fixture(tmp_path)
    with pytest.raises(ValueError, match="fingerprint"):
        EXPORT["create"](tmp_path, "incorrect fingerprint")
    assert not (tmp_path / "runs/p2/sanitised-repo").exists()


def test_unreviewed_binary_is_rejected(tmp_path: Path) -> None:
    fixture(tmp_path)
    (tmp_path / "src/opaque.bin").write_bytes(bytes([0xFF, 0xFE]))
    subprocess.run(["git", "-C", str(tmp_path), "add", "src/opaque.bin"], check=True)
    with pytest.raises(ValueError, match="Unreviewed binary"):
        EXPORT["plan"](tmp_path)
