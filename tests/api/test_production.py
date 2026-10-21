"""The local review serves only built assets alongside the existing API."""

from pathlib import Path

from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from macrolab.api.app import create_app


def test_production_assets_and_api_share_origin_without_exposing_checkout(tmp_path: Path) -> None:
    dist = tmp_path / "web/dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html><title>MacroLab local review</title></html>")
    (dist / "assets").mkdir()
    (dist / "assets/app.js").write_text("export const build = 'local';")
    (tmp_path / "private.txt").write_text("Never serve the checkout root")
    (dist / "outside.txt").symlink_to(tmp_path / "private.txt")
    client = TestClient(create_app(static_directory=dist))
    assert "MacroLab local review" in client.get("/").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/health").json()["network_binding"] == "127.0.0.1"
    assert client.get("/models").status_code == 200
    assert client.get("/private.txt").status_code == 404
    assert client.get("/outside.txt").status_code == 404
    assert client.get("/", headers={"host": "external.example"}).status_code == 400


def test_unbuilt_clone_explains_the_build_step_and_keeps_api_available(tmp_path: Path) -> None:
    client = TestClient(create_app(static_directory=tmp_path / "absent"))
    assert client.get("/").status_code == 503
    assert "make web-build" in client.get("/").text
    assert client.get("/health").status_code == 200


def test_api_only_embedding_keeps_later_harness_mounts_reachable(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("Production frontend")
    (tmp_path / "harness.html").write_text("Numerical parity harness")
    app = create_app(static_directory=tmp_path, serve_frontend=False)
    app.mount("/runtime", StaticFiles(directory=tmp_path))
    client = TestClient(app)
    assert client.get("/").status_code == 404
    assert client.get("/runtime/harness.html").text == "Numerical parity harness"
    assert client.get("/health").status_code == 200
