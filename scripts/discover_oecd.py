"""Bounded, explicit OECD metadata discovery; ignored snapshots only."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from macrolab.data.sources.http import SourceClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--request", action="append", nargs=2, metavar=("ID", "PATH"), required=True
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = SourceClient(
        root,
        "g1-oecd-discovery-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f"),
        timeout=45,
        retries=0,
        max_bytes=40_000_000,
        pause=2,
    )
    for identifier, path in args.request:
        if not path.startswith("https://sdmx.oecd.org/public/rest/"):
            raise ValueError("Discovery requests must use the official OECD SDMX API")
        result = client.fetch(
            "OECD",
            identifier,
            path,
            "text/csv" if "/data/" in path else "application/vnd.sdmx.structure+xml;version=2.1",
        )
        print(json.dumps(asdict(result.record)), flush=True)


if __name__ == "__main__":
    main()
