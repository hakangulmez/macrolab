"""Archive and independently audit keyless official EIA Brent data for P2 only."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from macrolab.data.sources.eia import (
    SERIES_ID,
    TABLE_URL,
    TITLE,
    WORKBOOK_URL,
    parse_table,
    parse_workbook,
)
from macrolab.data.sources.eia import audit as audit_values
from macrolab.data.sources.http import SourceClient

ROOT = Path(__file__).resolve().parents[1]


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write(path: Path, payload: dict[str, Any], *, immutable: bool = False) -> None:
    content = json.dumps(payload, indent=2, allow_nan=False).encode() + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if path.read_bytes() != content:
            raise ValueError("Refusing to alter an archived EIA candidate input")
        return
    path.write_bytes(content)


def fetch(root: Path) -> list[dict[str, Any]]:
    snapshot = "p2-eia-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    client = SourceClient(root, snapshot, retries=0)
    records = []
    for name, url, mime in (
        ("brent-monthly-xls", WORKBOOK_URL, "application/vnd.ms-excel"),
        ("brent-monthly-table", TABLE_URL, "text/html"),
    ):
        result = client.fetch("EIA", name, url, mime)
        records.append(asdict(result.record))
        if result.record.error:
            raise ValueError(f"Official EIA retrieval failed: {result.record.error}")
    return records


def verify_records(
    root: Path, records: list[dict[str, Any]]
) -> dict[str, tuple[bytes, dict[str, Any]]]:
    verified = {}
    for record in records:
        url = record["url"]
        if url not in {WORKBOOK_URL, TABLE_URL} or url in verified:
            raise ValueError("The EIA input requires exactly one workbook and one official table")
        path = root / str(record["raw_path"])
        if path.is_symlink() or not path.resolve().is_relative_to(
            (root / "data/raw/EIA").resolve()
        ):
            raise ValueError("EIA raw input must remain in its ignored source archive")
        content = path.read_bytes()
        if (
            record["status"] != 200
            or not record["body_complete"]
            or digest(content) != record["sha256"]
            or len(content) != record["size_bytes"]
        ):
            raise ValueError("EIA raw input differs from the complete archived fetch")
        verified[url] = content, record
    if set(verified) != {WORKBOOK_URL, TABLE_URL}:
        raise ValueError("Both official EIA source formats are required")
    return verified


def prepare(root: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    verified = verify_records(root, records)
    workbook, workbook_record = verified[WORKBOOK_URL]
    table, table_record = verified[TABLE_URL]
    rows = parse_workbook(workbook)
    values, release = parse_table(table)
    audit = audit_values(rows, values)
    snapshot = workbook_record["snapshot_id"]
    for row in rows:
        row.update(
            country="GLOBAL",
            concept_id="oil_brent",
            source="EIA",
            source_series_id=SERIES_ID,
            source_url=WORKBOOK_URL,
            unit="USD_PER_BARREL",
            unit_label="US dollars per barrel",
            unit_mult=0,
            sa_flag="NSA",
            price_basis="nominal",
            base_year=None,
            freq="M",
            obs_status="reported",
            shared=True,
            flags=[],
            raw_path=workbook_record["raw_path"],
            attribution=(
                f"Source: U.S. Energy Information Administration (EIA), {TITLE}, monthly "
                f"({SERIES_ID}); released {release}; accessed {workbook_record['retrieved_utc']}. "
                f"Published source table: {TABLE_URL}. EIA data are public domain. "
                "Frequency conversion and log transformations are MacroLab calculations."
            ),
            terms_status="EIA public-domain data; independent publication approval pending",
            definition=(
                "Monthly Europe Brent spot price, free on board; nominal US dollars per barrel."
            ),
        )
    payload = {
        "schema_version": 1,
        "snapshot_id": snapshot,
        "source_release_date": release,
        "retrieved_utc": workbook_record["retrieved_utc"],
        "source_records": records,
        "audit": audit,
        "rows": rows,
    }
    path = root / "data/processed/p2-eia" / snapshot / "brent.json"
    write(path, payload, immutable=True)
    marker = {
        "schema_version": 1,
        "snapshot_id": snapshot,
        "path": str(path.relative_to(root)),
        "sha256": digest(path.read_bytes()),
        "observations": len(rows),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "source_release_date": release,
        "retrieved_utc": workbook_record["retrieved_utc"],
        "audit": audit,
        "workbook_sha256": workbook_record["sha256"],
        "table_sha256": table_record["sha256"],
    }
    write(root / "runs/p2/eia/input.json", marker)
    write(root / "runs/p2/eia/audit.json", {**marker, "source_records": records})
    return marker


def load(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    marker = json.loads((root / "runs/p2/eia/input.json").read_text())
    path = root / marker["path"]
    if path.is_symlink() or not path.resolve().is_relative_to(
        (root / "data/processed/p2-eia").resolve()
    ):
        raise ValueError("P2 EIA input must remain inside the dedicated processed archive")
    content = path.read_bytes()
    if digest(content) != marker["sha256"]:
        raise ValueError("P2 EIA input checksum differs from its audited marker")
    data = json.loads(content)
    if not data["audit"]["passed"] or data["audit"] != marker["audit"]:
        raise ValueError("P2 EIA data requires the complete independent audit")
    verify_records(root, data["source_records"])
    return data["rows"], marker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Explicit live retrieval; default replays archived files",
    )
    args = parser.parse_args()
    records_path = ROOT / "runs/p2/eia/fetch-records.json"
    if args.fetch:
        records = fetch(ROOT)
        records_path.parent.mkdir(parents=True, exist_ok=True)
        records_path.write_text(json.dumps(records, indent=2) + "\n")
    else:
        records = json.loads(records_path.read_text())
    marker = prepare(ROOT, records)
    print(
        json.dumps(
            {
                key: marker[key]
                for key in ("snapshot_id", "observations", "first_date", "last_date", "audit")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
