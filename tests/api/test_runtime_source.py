"""A portable wheel must use this checkout's editable source installation."""

import runpy
from pathlib import Path

import pytest

import macrolab
from macrolab.export import script as export_script

BUILD = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/build_runtime_assets.py")
)["build_wheel"]


@pytest.mark.parametrize("module", [macrolab, export_script])
def test_other_checkout_module_is_rejected_before_archiving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: object
) -> None:
    monkeypatch.setattr(module, "__file__", str(tmp_path / "another-checkout/module.py"))

    def unexpected_archive() -> bytes:
        raise AssertionError("A conflicting source installation must not be archived")

    monkeypatch.setattr(export_script, "source_archive", unexpected_archive)
    with pytest.raises(ValueError, match="this checkout's src/macrolab"):
        BUILD()


def test_current_checkout_source_passes_identity_check_before_archiving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reached_archive() -> bytes:
        raise RuntimeError("Identity check passed; do not create runtime assets in this test")

    monkeypatch.setattr(export_script, "source_archive", reached_archive)
    with pytest.raises(RuntimeError, match="Identity check passed"):
        BUILD()
