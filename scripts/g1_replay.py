"""Rebuild with HTTP opening blocked and prove raw snapshots were not modified."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from macrolab.data.pipeline import run
from macrolab.data.snapshot import sha256_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    raw_manifest = root / "data/manifests/raw_manifest.jsonl"
    before = sha256_file(raw_manifest)
    with patch(
        "urllib.request.OpenerDirector.open",
        side_effect=AssertionError("Offline rebuild attempted an HTTP request"),
    ) as network:
        result = run(root, snapshot_id=args.snapshot, offline=True)
    after = sha256_file(raw_manifest)
    evidence = {
        "snapshot_id": args.snapshot,
        "processed_destination": result["destination"],
        "processing_fingerprint": result["processing_inputs"]["fingerprint"],
        "http_attempts": network.call_count,
        "raw_manifest_before": before,
        "raw_manifest_after": after,
        "raw_manifest_unchanged": before == after,
        "replay_comparison": result.get("replay_comparison"),
    }
    gate = "g1_1" if result.get("base_snapshot") else "g1"
    path = root / "runs" / gate / "offline_guard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n")
    if network.call_count or before != after:
        raise SystemExit("Offline replay modified raw evidence or attempted the network")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
