"""Generate metadata-only G1.1 coverage and scoped audit reports from a completed snapshot.

Use --check to validate and render in memory without writing reports. No provider
requests or observation-value exports occur. A recorded base snapshot is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from macrolab.data.sources.http import validate_url

ROOT = Path(__file__).resolve().parents[1]
STATUSES = ("available", "available_note", "limited", "missing")
AUDIT_SCOPE = {"ppi", "cpi", "cpi_core", "cli"}


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    def cell(value: Any) -> str:
        return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")

    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(cell(item) for item in row) + " |" for row in rows),
        "",
    ]


def source_link(source: str, url: str) -> str:
    validate_url(url)
    return f"[{source}]({url})"


def counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    totals = Counter(card["status"] for card in cards)
    return {status: totals[status] for status in STATUSES}


def load_evidence(root: Path) -> dict[str, Any]:
    processed = (root / "data/processed").resolve()
    directory = (processed / "current").resolve(strict=True)
    if not directory.is_relative_to(processed) or directory == processed:
        raise ValueError("Current snapshot must remain inside project data/processed")
    manifest = json.loads((directory / "processed_manifest.json").read_text())
    base = manifest.get("base_snapshot")
    if not isinstance(base, dict):
        raise ValueError("G1.1 reports require a completed snapshot with base_snapshot provenance")
    if set(manifest.get("audit_scope", [])) != AUDIT_SCOPE:
        raise ValueError("G1.1 report audit scope must be ppi, cpi, cpi_core and cli")
    base_path = (root / base["destination"] / "processed_manifest.json").resolve(strict=True)
    if not base_path.is_relative_to(processed):
        raise ValueError("Base snapshot must remain inside project data/processed")
    base_bytes = base_path.read_bytes()
    base_manifest = json.loads(base_bytes)
    if (
        hashlib.sha256(base_bytes).hexdigest() != base.get("manifest_sha256")
        or base_manifest.get("snapshot_id") != base.get("snapshot_id")
        or base_manifest.get("audit_summary") != base.get("audit_summary")
        or base.get("audit_summary", {}).get("passed") is not True
    ):
        raise ValueError("Recorded parent snapshot or audit evidence does not verify")

    evidence: dict[str, Any] = {"manifest": manifest}
    for name in ("series_cards", "countries", "audit", "fallbacks", "selection_ledger"):
        filename = f"{name}.json"
        payload = (directory / filename).read_bytes()
        record = manifest["files"][filename]
        if record["sha256"] != hashlib.sha256(payload).hexdigest() or record["bytes"] != len(
            payload
        ):
            raise ValueError(f"Processed evidence hash or size differs: {filename}")
        evidence[name] = json.loads(payload)
    cards = evidence["series_cards"]
    concepts = sorted({card["concept_id"] for card in cards})
    countries = {country["iso3"] for country in evidence["countries"]}
    keys = {(card["concept_id"], card["country"]) for card in cards}
    if (
        len(cards) != 1404
        or len(keys) != len(cards)
        or keys != {(concept, country) for concept in concepts for country in countries}
    ):
        raise ValueError("Coverage must contain all 1,404 unique concept/country cells")
    for card in cards:
        reasons = card.get("reason_codes")
        if (
            card["status"] not in STATUSES
            or not isinstance(reasons, list)
            or not reasons
            or len(reasons) != len(set(reasons))
            or card.get("reason_code") != reasons[0]
        ):
            raise ValueError("Coverage cards require four-class status and explicit reason codes")
    proof = manifest.get("unchanged_proof", {})
    if (
        set(proof.get("concept_ids", [])) != set(concepts) - AUDIT_SCOPE
        or proof.get("before_hash") != proof.get("after_hash")
        or not proof.get("before_hash")
        or any(
            proof.get(key) is not True
            for key in ("passed", "profiles_unchanged", "variants_unchanged", "countries_unchanged")
        )
    ):
        raise ValueError("The complete unaffected concept and metadata proof is required")
    audit = evidence["audit"]
    checks = audit["checks"]
    if len(checks) != 36 or set(check["concept_id"] for check in checks) != AUDIT_SCOPE:
        raise ValueError("The scoped audit must record 36 comparisons across four concepts")
    for concept in sorted(AUDIT_SCOPE):
        records = [check for check in checks if check["concept_id"] == concept]
        by_country = Counter(check["country"] for check in records)
        if (
            len(by_country) != 3
            or set(by_country.values()) != {3}
            or len({(check["country"], check["date"]) for check in records}) != 9
        ):
            raise ValueError(
                f"Audit must contain three countries × three distinct dates: {concept}"
            )
    if audit["required_checks"] != 36 or audit["performed_checks"] != len(checks):
        raise ValueError("Audit totals disagree with the comparison records")
    for key, status in (
        ("matched", "matched"),
        ("mismatches", "mismatch"),
        ("unavailable", "unavailable"),
    ):
        if audit[key] != sum(check["status"] == status for check in checks):
            raise ValueError("Audit outcome totals disagree with the comparison records")
    expected_fallbacks = [item for item in evidence["selection_ledger"] if item["fallback"]]

    def canonical(items: list[dict[str, Any]]) -> list[str]:
        return sorted(json.dumps(item, sort_keys=True) for item in items)

    if canonical(expected_fallbacks) != canonical(evidence["fallbacks"]):
        raise ValueError("Fallback report must include every selected fallback in the ledger")
    selected = {
        (card["country"], card["concept_id"], segment["source"], segment["source_series_id"])
        for card in cards
        for segment in card["source_segments"]
    }
    for item in expected_fallbacks:
        if (
            item["country"],
            item["concept_id"],
            item["selected_source"],
            item["source_series_id"],
        ) not in selected:
            raise ValueError("A fallback ledger item is not a currently selected source segment")
    baseline_path = root / "runs/g1_1/baseline_coverage.json"
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
    if baseline is not None and (
        not isinstance(baseline, list)
        or len(baseline) != len(cards)
        or {(item["concept_id"], item["country"]) for item in baseline} != keys
        or any(item["status"] not in STATUSES for item in baseline)
    ):
        raise ValueError("Stored baseline must use the same cells and four-class taxonomy")
    evidence["baseline"] = baseline
    return evidence


def coverage_report(evidence: dict[str, Any]) -> str:
    manifest, cards = evidence["manifest"], evidence["series_cards"]
    concepts = sorted({card["concept_id"] for card in cards})
    by_cell = {(card["country"], card["concept_id"]): card for card in cards}
    lines = [
        "# G1.1 coverage and selected fallbacks",
        "",
        f"Snapshot `{manifest['snapshot_id']}`; as of {manifest['as_of_date']}. "
        "DRAFT local metadata report. No observations are reproduced; no publication is approved.",
        "",
        f"{len(evidence['countries'])} countries/aggregates × {len(concepts)} concepts "
        f"= {len(cards):,} coverage cells (33 national indicators and 3 global factors).",
        "",
        "`available` has no classified coverage caveat. `available_note` retains a definition "
        "or method note without a model-relevant data limit. `limited` identifies stale history, "
        "internal gaps, a start after 2005-12-31 and after the requested sample, unknown seasonal "
        "adjustment relevant to modelling, or no observation in the requested sample. `missing` "
        "means no eligible observed series. A shorter start through 2005-12-31 is a note. "
        "Global sharing, rate timing and annual native frequency are notes. Special-period and "
        "outlier flags do not themselves change the coverage class or any value.",
        "",
        "The actual available sample is the first observed period on or after the requested "
        "start through the latest observed period. It may contain the explicitly reported gaps. "
        "The default requested start is 1999 Q1, adjusted for adoption where relevant. "
        "These are per-series availability ranges; no model or common estimation sample has "
        "been produced at this gate. Native monthly, quarterly and annual periods are retained.",
        "",
        "## Overall status counts",
        "",
    ]
    rows: list[list[Any]] = []
    if evidence["baseline"] is not None:
        rows.append(["G1 baseline reclassified", *counts(evidence["baseline"]).values()])
    rows.append(["G1.1 current", *counts(cards).values()])
    lines += table(["Snapshot classification", *STATUSES], rows)
    lines += [
        "The baseline counts use the saved four-class classification in "
        "`runs/g1_1/baseline_coverage.json`; the historical three-class G1 totals are "
        "not directly comparable.",
        "",
        "## Counts by concept",
        "",
    ]
    lines += table(
        ["Concept", *STATUSES],
        [
            [concept, *counts([card for card in cards if card["concept_id"] == concept]).values()]
            for concept in concepts
        ],
    )
    lines += [
        "## Every reason code by concept",
        "",
        "A cell may have several reasons. Each reason is counted once per cell, so "
        "reason counts are not mutually exclusive and need not sum to the cell count.",
        "",
    ]
    reason_rows: list[list[Any]] = []
    for concept in concepts:
        reasons = Counter(
            reason
            for card in cards
            if card["concept_id"] == concept
            for reason in set(card["reason_codes"])
        )
        reason_rows.extend([concept, reason, number] for reason, number in sorted(reasons.items()))
    lines += table(["Concept", "Reason code", "Cells"], reason_rows)
    lines += ["## Full concept × country matrix", ""]
    lines += table(
        [
            "Concept",
            "Country",
            "Status",
            "Frequency",
            "First",
            "Last",
            "Actual available sample",
            "Primary reason code",
            "All reason codes",
        ],
        [
            [
                card["concept_id"],
                card["country"],
                card["status"],
                card["frequency"],
                card["first_date"],
                card["last_date"],
                f"{card['actual_available_start']} → {card['last_date']}"
                if card["actual_available_start"]
                else None,
                card["reason_code"],
                ", ".join(card["reason_codes"]),
            ]
            for card in sorted(cards, key=lambda row: (row["concept_id"], row["country"]))
        ],
    )
    stale = [card for card in cards if card["stale"]]
    lines += [
        "## Remaining stale histories",
        "",
        f"{len(stale)} cells retain stale histories; none is presented as current.",
        "",
    ]
    lines += table(
        ["Country", "Concept", "Last", "Status", "Reasons", "Selected sources"],
        [
            [
                card["country"],
                card["concept_id"],
                card["last_date"],
                card["status"],
                ", ".join(card["reason_codes"]),
                "; ".join(
                    sorted(
                        {
                            source_link(segment["source"], segment["source_url"])
                            for segment in card["source_segments"]
                        }
                    )
                ),
            ]
            for card in sorted(stale, key=lambda row: (row["concept_id"], row["country"]))
        ],
    )
    fallbacks = evidence["fallbacks"]
    retained = sum(item["concept_id"] not in AUDIT_SCOPE for item in fallbacks)
    lines += [
        "## All selected provider fallbacks",
        "",
        f"{len(fallbacks)} actual selected fallbacks, including {retained} in unchanged "
        "concepts. This is the complete merged selection ledger, not only new fetches. "
        "A fallback supplies a selected series; observations are not filled from a "
        "different source. The separately specified policy-rate adoption splice remains "
        "recorded in the source cards.",
        "",
    ]
    fallback_rows: list[list[Any]] = []
    for item in sorted(fallbacks, key=lambda row: (row["concept_id"], row["country"])):
        card = by_cell[(item["country"], item["concept_id"])]
        segments = [
            segment
            for segment in card["source_segments"]
            if segment["source"] == item["selected_source"]
            and segment["source_series_id"] == item["source_series_id"]
        ]
        fallback_rows.append(
            [
                item["country"],
                item["concept_id"],
                item["selected_source"],
                ", ".join(item["prior_sources"]),
                item["source_series_id"],
                min(segment["first_date"] for segment in segments),
                max(segment["last_date"] for segment in segments),
                "; ".join(
                    sorted(
                        {
                            source_link(segment["source"], segment["source_url"])
                            for segment in segments
                        }
                    )
                ),
                "Refreshed scope" if item["concept_id"] in AUDIT_SCOPE else "Unchanged concept",
            ]
        )
    lines += table(
        [
            "Country",
            "Concept",
            "Selected provider",
            "Earlier priorities",
            "Selected series",
            "First",
            "Last",
            "Official source",
            "Refresh scope",
        ],
        fallback_rows,
    )
    return "\n".join(lines).rstrip() + "\n"


def audit_report(evidence: dict[str, Any]) -> str:
    manifest, audit = evidence["manifest"], evidence["audit"]
    base, proof = manifest["base_snapshot"], manifest["unchanged_proof"]
    parent = base["audit_summary"]
    lines = [
        "# G1.1 independent audit — scoped refresh",
        "",
        f"Snapshot `{manifest['snapshot_id']}`; as of {manifest['as_of_date']}. "
        "DRAFT local metadata report; no source or transformed observation values are included.",
        "",
        "## New audit scope",
        "",
        "Only `ppi`, `cpi`, `cpi_core` and `cli` are audited again in G1.1: three countries "
        "and three distinct dates per concept, nine comparisons each, 36 in total. "
        + audit["method"],
        "",
        "The independent reader reopens archived official machine-readable payloads and "
        "verifies the source period and identifying dimensions before comparing the value. "
        "The direct official download/API links below identify the source; there is no HTML "
        "observation scraping. Absolute tolerance "
        f"{audit['tolerance_absolute']}; relative tolerance {audit['tolerance_relative']}.",
        "",
    ]
    lines += table(
        [
            "Audit evidence",
            "Required",
            "Performed",
            "Matched",
            "Mismatches",
            "Unavailable",
            "Passed",
        ],
        [
            [
                "G1.1 new scope",
                *(
                    audit[key]
                    for key in (
                        "required_checks",
                        "performed_checks",
                        "matched",
                        "mismatches",
                        "unavailable",
                        "passed",
                    )
                ),
            ],
            [
                "Parent G1 historical record — not rerun",
                *(
                    parent[key]
                    for key in (
                        "required_checks",
                        "performed_checks",
                        "matched",
                        "mismatches",
                        "unavailable",
                        "passed",
                    )
                ),
            ],
        ],
    )
    lines += [
        "## Parent audit and unchanged-data provenance",
        "",
        f"Parent snapshot `{base['snapshot_id']}` at `{base['destination']}`; manifest "
        f"SHA-256 `{base['manifest_sha256']}`. Its audit remains preserved as historical "
        "evidence and was not rerun for unchanged concepts. The two audit rows above "
        "must not be added together as a count of distinct observations.",
        "",
        f"The unchanged proof covers {len(proof['concept_ids'])} concepts and "
        f"{proof['rows']:,} stored rows, including their metadata. Before/after "
        f"canonical hash: `{proof['before_hash']}`. Equal hashes and unchanged profiles, "
        "global variants and countries are verified in the processed manifest. "
        "This supports preserving the prior audit evidence; it is not a new source audit.",
        "",
        "Unaffected concepts: " + ", ".join(f"`{c}`" for c in sorted(proof["concept_ids"])) + ".",
        "",
        "## Nine comparisons per refreshed concept",
        "",
    ]
    lines += table(
        ["Concept", "Countries", "Required", "Performed", "Matched", "Mismatches", "Unavailable"],
        [
            [
                concept,
                ", ".join(
                    sorted(
                        {
                            check["country"]
                            for check in audit["checks"]
                            if check["concept_id"] == concept
                        }
                    )
                ),
                9,
                sum(check["concept_id"] == concept for check in audit["checks"]),
                *(
                    sum(
                        check["concept_id"] == concept and check["status"] == status
                        for check in audit["checks"]
                    )
                    for status in ("matched", "mismatch", "unavailable")
                ),
            ]
            for concept in sorted(AUDIT_SCOPE)
        ],
    )
    lines += ["## All 36 country/date/source comparisons", ""]
    ordered = sorted(
        audit["checks"], key=lambda row: (row["concept_id"], row["country"], row["date"])
    )
    lines += table(
        ["Concept", "Country", "Date", "Official source", "Source series", "Result"],
        [
            [
                item["concept_id"],
                item["country"],
                item["date"],
                source_link(item["source"], item["source_url"]),
                item["source_series_id"],
                item["status"],
            ]
            for item in ordered
        ],
    )
    failures = [item for item in ordered if item["status"] != "matched"]
    lines += ["## Mismatches and unavailable comparisons", ""]
    if failures:
        lines += table(
            ["Concept", "Country", "Date", "Result", "Evidence"],
            [
                [
                    item["concept_id"],
                    item["country"],
                    item["date"],
                    item["status"],
                    "Review archived audit.json; no observation values are reproduced here.",
                ]
                for item in failures
            ],
        )
    else:
        lines += [
            "None: all 36 comparisons matched; zero mismatches and zero unavailable checks.",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing reports")
    args = parser.parse_args()
    evidence = load_evidence(ROOT)
    reports = {
        "COVERAGE_G1_1.md": coverage_report(evidence),
        "DATA_AUDIT_G1_1.md": audit_report(evidence),
    }
    if not args.check:
        for name, content in reports.items():
            (ROOT / "docs" / name).write_text(content)
    print(
        json.dumps(
            {
                "written": not args.check,
                "reports": list(reports),
                "snapshot_id": evidence["manifest"]["snapshot_id"],
                "coverage_cells": len(evidence["series_cards"]),
                "status_counts": counts(evidence["series_cards"]),
                "audit_records": len(evidence["audit"]["checks"]),
                "selected_fallbacks": len(evidence["fallbacks"]),
            }
        )
    )


if __name__ == "__main__":
    main()
