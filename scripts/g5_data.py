"""Build G5 additions from checksum-verified official responses without a network call."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from macrolab.data.pipeline import write_json
from macrolab.data.snapshot import sha256_file
from macrolab.data.sources.http import FetchRecord, FetchResult
from macrolab.data.sources.v1 import REQUESTS, fetch_v1

ROOT = Path(__file__).resolve().parents[1]


class RecordedSources:
    """Replay an explicit allowlist of archived retrieval IDs, verified on every read."""

    def __init__(self, root: Path, records: list[dict[str, Any]]) -> None:
        self.root = root
        self.records = {r["url"]: r for r in records}

    def fetch(self, source: str, probe_id: str, url: str, accept: str) -> FetchResult:
        data = self.records[url]
        record = FetchRecord(**data)
        if record.source != source or record.status != 200 or not record.body_complete:
            raise ValueError("Recorded G5 response is incomplete or has the wrong source")
        path = (self.root / str(record.raw_path)).resolve()
        if not path.is_relative_to((self.root / "data/raw").resolve()):
            raise ValueError("Raw source path escapes the project archive")
        if sha256_file(path) != record.sha256 or path.stat().st_size != record.size_bytes:
            raise ValueError("G5 raw source checksum or size mismatch")
        return FetchResult(path.read_bytes(), record)


def load(root: Path = ROOT) -> dict[str, Any]:
    marker = json.loads((root / "runs/g5/data-inputs.json").read_text())
    countries = json.loads((root / "runs/p2/public/data/manifest.json").read_text())["countries"]
    client = RecordedSources(root, marker["source_records"])
    return fetch_v1(client, countries, date.fromisoformat(marker["as_of_date"]))  # type: ignore[arg-type]


def main() -> None:
    path = ROOT / "runs/g5/data-inputs.json"
    if not path.exists():
        records = [
            json.loads(line)
            for line in (ROOT / "data/manifests/raw_manifest.jsonl").read_text().splitlines()
        ]
        chosen = []
        for _source, url, _mime in REQUESTS.values():
            candidates = [
                r
                for r in records
                if r["url"] == url
                and r["status"] == 200
                and r["snapshot_id"].startswith("g5-discovery-")
            ]
            if not candidates:
                raise ValueError(f"Required G5 archive is missing: {url}")
            chosen.append(candidates[-1])
        write_json(path, {"as_of_date": "2026-10-21", "source_records": chosen})
    result = load()
    write_json(ROOT / "runs/g5/source-additions.json", result)
    variants = result["variant_rows"]
    coverage = []
    for key in sorted({row["variant"] for row in variants}):
        rows = sorted([row for row in variants if row["variant"] == key], key=lambda r: r["date"])
        coverage.append(
            {
                "variant": key,
                "country": rows[0]["country"],
                "concept_id": rows[0]["concept_id"],
                "start": rows[0]["date"],
                "end": rows[-1]["date"],
                "observations": len(rows),
                "base_year": rows[0]["base_year"],
                "sa_flag": rows[0]["sa_flag"],
                "source_series_ids": sorted({r["source_series_id"] for r in rows}),
            }
        )
    evidence = {
        "audit": result["audit"],
        "coverage": coverage,
        "shared_default_country_counts": dict(Counter(r["country"] for r in result["rows"])),
        "source_records": json.loads(path.read_text())["source_records"],
    }
    write_json(ROOT / "docs/process/G5_DATA_EVIDENCE.json", evidence)
    print(json.dumps({"audit": result["audit"], "coverage": coverage}, indent=2))


if __name__ == "__main__":
    main()
