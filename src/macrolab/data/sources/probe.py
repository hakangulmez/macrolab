"""Run bounded public-source probes; keep every response outside git."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from macrolab.data.sources.http import SourceClient
from macrolab.data.sources.parsers import parse_response


def probe_one(client: SourceClient, config: dict[str, Any]) -> dict[str, Any]:
    fetched = client.fetch(config["provider"], config["id"], config["url"], config["accept"])
    result: dict[str, Any] = {
        "id": config["id"],
        "provider": config["provider"],
        "dataset_candidate": config["dataset_candidate"],
        "series_candidate": config["series_candidate"],
        "fetch": asdict(fetched.record),
        "status": "unavailable",
        "parsed": None,
        "error": fetched.record.error,
    }
    if fetched.record.status != 200 or fetched.body is None:
        return result
    try:
        result["parsed"] = parse_response(config["parser"], fetched.body)
        result["status"] = "verified_observations"
    except (
        ValueError,
        KeyError,
        IndexError,
        StopIteration,
        UnicodeError,
        ImportError,
        ET.ParseError,
        BadZipFile,
    ) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def public_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Retain provenance/counts, but never copy observation values into git."""
    parsed = result.get("parsed")
    metadata = (
        {key: value for key, value in parsed.items() if key != "example_observation"}
        if parsed
        else None
    )
    return {**result, "parsed": metadata}


def source_document(evidence: dict[str, Any]) -> str:
    lines = [
        "# G0 official-source probe evidence",
        "",
        f"Evidence set: `{evidence['snapshot_id']}`. Retrieval times are UTC.",
        evidence.get("evidence_note", "One bounded diagnostic run; no G1 data snapshot."),
        "",
        "These are bounded access and parsing probes, not validated G1 concept mappings. "
        "A successful status requires finite observations and source response metadata; "
        "HTTP success alone is insufficient. Candidate IDs remain unverified "
        "where the probe failed.",
        "",
        "Raw response bodies and observation values are stored only in ignored "
        "`data/` and `runs/`. "
        "The tracked `docs/probe_evidence.json` contains metadata, checksums and counts "
        "without observation values.",
        "",
        "| Provider / probe | Status | Parsed observations | Details |",
        "|---|---|---:|---|",
    ]
    for result in evidence["probes"]:
        count = result["parsed"]["observation_count"] if result["parsed"] else "—"
        detail = result.get("error") or "Response parsed; concept mapping deferred to G1."
        lines.append(
            f"| {result['provider']} / `{result['id']}` | {result['status']} | "
            f"{count} | {str(detail).replace('|', '/')} |"
        )
    for result in evidence["probes"]:
        fetch = result["fetch"]
        lines.extend(
            [
                "",
                f"## {result['provider']} — {result['id']}",
                "",
                f"- Base URL: `{urllib.parse.urlsplit(fetch['url']).scheme}://"
                f"{urllib.parse.urlsplit(fetch['url']).netloc}/`",
                f"- Example query: <{fetch['url']}>",
                f"- Final URL: {fetch['final_url'] or 'No response'}",
                f"- Dataset candidate: `{result['dataset_candidate']}`",
                f"- Series candidate: `{result['series_candidate']}`",
                f"- Retrieval: `{fetch['retrieved_utc']}`; HTTP: `{fetch['status']}`; "
                f"MIME: `{fetch['mime_type']}`.",
                f"- SHA-256: `{fetch['sha256']}`; complete body: `{fetch['body_complete']}`.",
            ]
        )
        if result["parsed"]:
            lines.append(
                f"- Observed period range: `{result['parsed']['first_period']}` "
                f"to `{result['parsed']['last_period']}`."
            )
    lines.extend(
        [
            "",
            "## Operational boundary",
            "",
            "The stdlib client disables environment proxies and supplies no cookies, "
            "authentication, API keys "
            "or credentials. HTTPS hosts and every redirect are checked "
            "against an explicit allowlist. "
            "Requests use a project-named User-Agent, bounded timeout, "
            "one retry for transient errors, "
            "a response-size cap, and a pause between probes. "
            "Truncated responses are not retained as complete snapshots.",
            "",
            "Use `python -m macrolab.data.sources.probe` from this repository after setup. "
            "Use `--skip-terms` for data-only diagnostics. The command is explicitly live-network; "
            "`make quick` and `make test` do not call it. "
            "Probe snapshots are diagnostic runs with unique IDs, "
            "not complete G1 data snapshots. Previous raw files are never overwritten.",
            "",
            "FRED is an access diagnostic only. FEDFUNDS is not adopted as a data mapping: "
            "the original "
            "publisher/source priority and series-specific rights still govern G1.",
            "",
            "Licence review is in `DATA.md`. "
            "Availability, licensing and suitability are separate checks.",
        ]
    )
    return "\n".join(lines) + "\n"


def run(root: Path, *, skip_terms: bool = False, timeout: float = 25) -> dict[str, Any]:
    config = json.loads((root / "configs" / "source_probes.json").read_text())
    snapshot_id = "probe-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    client = SourceClient(root, snapshot_id, timeout=timeout)
    probes = []
    for index, item in enumerate(config["probes"]):
        if index:
            time.sleep(client.pause)
        result = probe_one(client, item)
        probes.append(result)
        print(
            json.dumps({"probe": item["id"], "status": result["status"], "error": result["error"]}),
            flush=True,
        )
    terms = []
    if not skip_terms:
        for item in config["terms"]:
            time.sleep(client.pause)
            fetched = client.fetch(item["provider"], item["id"], item["url"], "text/html")
            terms.append(
                {"id": item["id"], "provider": item["provider"], "fetch": asdict(fetched.record)}
            )
            print(
                json.dumps(
                    {
                        "terms": item["id"],
                        "status": fetched.record.status,
                        "error": fetched.record.error,
                    }
                ),
                flush=True,
            )
    result = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "scope": config["scope"],
        "provider_count": len({item["provider"] for item in probes}),
        "probe_count": len(probes),
        "verified_probe_count": sum(item["status"] == "verified_observations" for item in probes),
        "probes": probes,
        "terms": terms,
    }
    output = root / "runs" / "probes" / snapshot_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    evidence = {**result, "probes": [public_evidence(item) for item in probes]}
    (root / "docs" / "probe_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    (root / "docs" / "SOURCES.md").write_text(source_document(evidence))
    print(
        json.dumps(
            {
                "snapshot_id": snapshot_id,
                "providers": result["provider_count"],
                "probes": result["probe_count"],
                "verified": result["verified_probe_count"],
            }
        ),
        flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-terms", action="store_true")
    parser.add_argument("--timeout", type=float, default=25)
    args = parser.parse_args()
    root = Path.cwd()
    if not (root / "configs" / "source_probes.json").is_file():
        parser.error("Run from the MacroLab repository root")
    if not 1 <= args.timeout <= 60:
        parser.error("Timeout must be between 1 and 60 seconds")
    run(root, skip_terms=args.skip_terms, timeout=args.timeout)


if __name__ == "__main__":
    main()
