"""Immutable source snapshots and strictly offline replay of recorded requests."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from macrolab.data.sources.http import FetchRecord, FetchResult, SourceClient


class SnapshotError(RuntimeError):
    """A snapshot cannot be safely created or replayed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class SnapshotClient(SourceClient):
    """Cache repeated reads; offline mode never constructs an external request."""

    def __init__(
        self,
        root: Path,
        snapshot_id: str,
        *,
        offline: bool = False,
        as_of_date: date | None = None,
        timeout: float = 45,
    ) -> None:
        super().__init__(root, snapshot_id, timeout=timeout, max_bytes=160_000_000, pause=1.0)
        self.offline = offline
        self.as_of_date = as_of_date or date.today()
        self.cache: dict[tuple[str, str, str], FetchResult] = {}
        self.recorded: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.last_request: dict[str, float] = {}
        manifest = root / "data/manifests/raw_manifest.jsonl"
        if offline:
            if not manifest.is_file():
                raise SnapshotError("No raw manifest exists for offline reconstruction")
            for line in manifest.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                if record["snapshot_id"] == snapshot_id:
                    key = (record["source"], record["probe_id"], record["url"])
                    self.recorded[key] = record
            if not self.recorded:
                raise SnapshotError(f"No recorded requests for snapshot {snapshot_id}")

    def fetch(self, source: str, probe_id: str, url: str, accept: str) -> FetchResult:
        if source.upper() == "FRED" or "stlouisfed.org" in url:
            raise SnapshotError("FRED is disabled for G1; use the original publisher")
        key = (source, probe_id, url)
        if key in self.cache:
            return self.cache[key]
        if self.offline:
            record_data = self.recorded.get(key)
            if record_data is None:
                raise SnapshotError(
                    f"Offline snapshot has no recorded request: {source}/{probe_id}"
                )
            record = FetchRecord(**record_data)
            body = None
            if record.raw_path is not None:
                path = (self.root / record.raw_path).resolve()
                if not path.is_relative_to((self.root / "data/raw").resolve()):
                    raise SnapshotError("Raw path escapes the snapshot data directory")
                if sha256_file(path) != record.sha256:
                    raise SnapshotError(f"Raw snapshot checksum mismatch: {record.raw_path}")
                body = path.read_bytes()
                if len(body) != record.size_bytes or not record.body_complete:
                    raise SnapshotError(f"Incomplete raw response: {record.raw_path}")
            result = FetchResult(body, record)
        else:
            if any(s == source and p == probe_id for s, p, _ in self.cache):
                raise SnapshotError(f"Request identifier reused for a different URL: {probe_id}")
            host = urlsplit(url).netloc
            delay = self.pause - (time.monotonic() - self.last_request.get(host, 0.0))
            if delay > 0:
                time.sleep(delay)
            result = super().fetch(source, probe_id, url, accept)
            self.last_request[host] = time.monotonic()
        self.cache[key] = result
        return result


def verify_raw_manifest(root: Path, snapshot_id: str) -> dict[str, Any]:
    records = [
        json.loads(line)
        for line in (root / "data/manifests/raw_manifest.jsonl").read_text().splitlines()
        if line.strip()
    ]
    selected = [record for record in records if record["snapshot_id"] == snapshot_id]
    checked = 0
    for record in selected:
        if record["raw_path"] is None:
            continue
        path = (root / record["raw_path"]).resolve()
        if not path.is_relative_to((root / "data/raw").resolve()):
            raise SnapshotError("Manifest path outside raw data")
        if not record["body_complete"] or sha256_file(path) != record["sha256"]:
            raise SnapshotError(f"Raw checksum/completeness failure: {path}")
        if path.stat().st_size != record["size_bytes"]:
            raise SnapshotError(f"Raw size mismatch: {path}")
        checked += 1
    return {"request_records": len(selected), "response_hashes_verified": checked}
