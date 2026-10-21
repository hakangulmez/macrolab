"""Bounded harness server; production transport remains macrolab.api on loopback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

from macrolab.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text()) if args.fixture else None
    app = create_app(bundle=fixture["bundle"] if fixture else None, serve_frontend=False)
    app.mount("/live", create_app(serve_frontend=False))
    lock = json.loads((ROOT / "web/runtime/assets.lock.json").read_text())
    app.mount("/runtime", StaticFiles(directory=ROOT / "web/runtime"))
    app.mount("/assets", StaticFiles(directory=ROOT / ".cache/pyodide" / lock["pyodide_version"]))
    app.mount("/artifacts", StaticFiles(directory=ROOT / "runs/g2"))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
