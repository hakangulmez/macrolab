"""Generate metadata-only G1 coverage, fallback and independent audit reports."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    def cell(value: Any) -> str:
        return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")

    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(cell(item) for item in row) + " |" for row in rows),
        "",
    ]


def main() -> None:
    directory = ROOT / "data/processed/current"

    def read(name: str) -> Any:
        return json.loads((directory / name).read_text())

    manifest = read("processed_manifest.json")
    cards = read("series_cards.json")
    countries = read("countries.json")
    audit = read("audit.json")
    fallbacks = read("fallbacks.json")
    concepts = list(dict.fromkeys(card["concept_id"] for card in cards))
    cells = {(card["country"], card["concept_id"]): card for card in cards}
    summary = manifest["coverage_summary"]
    intro = (
        f"Snapshot `{manifest['snapshot_id']}`; as of {manifest['as_of_date']}. "
        "Generated from local processed evidence; contains metadata, not raw observations."
    )
    lines = ["# G1 coverage matrix", "", intro, ""]
    lines += [
        f"{len(countries)} units × {len(concepts)} families = {len(cards)} cells: "
        + ", ".join(
            f"{summary['status_counts'].get(s, 0)} {s}" for s in ("available", "partial", "missing")
        )
        + ".",
        "",
        "Available means verified observations with the requested history and no coverage "
        "caveat. Partial includes shorter history, gaps, stale data, unknown or differing "
        "adjustment, aggregate composition, source-definition or frequency caveats. Missing "
        "means no eligible observed series. Outlier flags never change values.",
        "",
        "Each matrix cell shows **status · first stored observation**. Starts are native "
        "periods; monthly, quarterly and annual histories are not upsampled. The default "
        "sample is 1999 Q1, later at euro adoption for shared-rate shocks, and later again "
        "at the first observed usable period. The actual per-series default start appears "
        "in `configs/indicators.yaml` and each local series card; model-specific common "
        "samples will be calculated and displayed in G2/G3.",
        "",
    ]
    lines += table(
        ["Concept", "Available", "Partial", "Missing", "First-date range (non-missing)"],
        [
            [
                concept,
                *(summary["by_concept"][concept][s] for s in ("available", "partial", "missing")),
                " – ".join((min(dates), max(dates)))
                if (
                    dates := [
                        card["first_date"]
                        for card in cards
                        if card["concept_id"] == concept and card["first_date"]
                    ]
                )
                else None,
            ]
            for concept in concepts
        ],
    )
    for offset in range(0, len(countries), 7):
        group = countries[offset : offset + 7]
        lines += ["## " + ", ".join(country["iso3"] for country in group), ""]
        lines += table(
            ["Concept"] + [country["iso3"] for country in group],
            [
                [concept]
                + [
                    f"{cells[(country['iso3'], concept)]['status']} · "
                    f"{cells[(country['iso3'], concept)]['first_date'] or '—'}"
                    for country in group
                ]
                for concept in concepts
            ],
        )
    lines += ["## Missing mappings", ""]
    lines += table(
        ["Concept", "Countries"],
        [
            [
                concept,
                ", ".join(
                    card["country"]
                    for card in cards
                    if card["concept_id"] == concept and card["status"] == "missing"
                ),
            ]
            for concept in concepts
            if summary["by_concept"][concept]["missing"]
        ],
    )
    lines += [
        "## Stale histories — visible warning",
        "",
        "These histories have no current eligible replacement in this mapped snapshot. "
        "They are partial and must not be presented as current observations.",
        "",
    ]
    lines += table(
        ["Country", "Concept", "Latest observed period", "Sources"],
        [
            [card["country"], card["concept_id"], card["last_date"], ", ".join(card["sources"])]
            for card in cards
            if card["stale"]
        ],
    )
    (ROOT / "docs/process/COVERAGE_G1.md").write_text("\n".join(lines).rstrip() + "\n")

    lines = [
        "# G1 source fallback ledger",
        "",
        intro,
        "",
        f"{len(fallbacks)} provider fallbacks selected. Every selected fallback is below.",
        "",
        "Selection first prefers current eligible histories, then the first provider "
        "with adequate history "
        "(120 monthly, 40 quarterly or 10 annual observations); if none qualifies, "
        "it uses the longest eligible history. No provider histories are stitched "
        "together except the specified national-to-ECB policy transition.",
        "",
    ]
    lines += table(
        ["Country", "Concept", "Selected provider", "Earlier priorities", "Series"],
        [
            [
                item["country"],
                item["concept_id"],
                item["selected_source"],
                ", ".join(item["prior_sources"]),
                item["source_series_id"],
            ]
            for item in fallbacks
        ],
    )
    lines += ["## Other explicitly retained alternatives", ""]
    lines += table(
        ["Country", "Concept", "Frequency", "Flags"],
        [
            [
                card["country"],
                card["concept_id"],
                card["frequency"],
                ", ".join(
                    flag
                    for flag in card["flags"]
                    if any(
                        token in flag
                        for token in ("native_frequency", "fallback", "aggregate", "composition")
                    )
                ),
            ]
            for card in cards
            if any(
                any(
                    token in flag
                    for token in ("native_frequency", "fallback", "aggregate", "composition")
                )
                for flag in card["flags"]
            )
        ],
    )
    lines += [
        "BIS remains the source for the shared US policy factor; FRED is disabled. "
        "Euro-area member policy rates use the BIS euro-area policy series from each "
        "documented adoption date, retaining national rates before adoption where present. "
        "The monthly BIS series is end-of-month. These are explicit instrument/timing "
        "choices, not interpolated observations.",
        "",
        "Pink Sheet is resolved from the official page on every new fetch; there is no "
        "fallback to the stale G0 file. Non-energy is the primary commodity index; energy "
        "is retained separately. See [source resolution](SOURCES.md).",
        "",
    ]
    lines += ["## Shared ECB policy transitions", ""]
    lines += table(
        ["Country", "Adoption boundary", "Post-adoption source"],
        [
            [country["iso3"], country["euro_adoption"], "BIS euro-area policy rate (shared)"]
            for country in countries
            if country.get("euro_adoption") and country["iso3"] != "EA"
        ],
    )
    (ROOT / "docs/process/FALLBACKS_G1.md").write_text("\n".join(lines).rstrip() + "\n")

    lines = [
        "# G1 independent data audit",
        "",
        intro,
        "",
        audit["method"],
        "",
        "Official APIs and downloadable source files are the source reference. "
        "No values are scraped from HTML where official machine-readable data exist. "
        "The reference reader is separate from each source adapter and verifies "
        "raw dates and identifying dimensions before comparing values. Derived "
        "spreads are independently recomputed from both source components.",
        "",
        audit["global_factor_note"],
        "",
        f"Required: {audit['required_checks']}; performed: {audit['performed_checks']}; "
        f"matched: {audit['matched']}; mismatches: {audit['mismatches']}; "
        f"unavailable: {audit['unavailable']}. Absolute tolerance "
        f"{audit['tolerance_absolute']}; relative tolerance {audit['tolerance_relative']}.",
        "",
    ]
    lines += table(
        ["Concept", "Countries", "Checks", "Matched", "Mismatches", "Unavailable"],
        [
            [
                item["concept_id"],
                ", ".join(item["countries"]),
                item["completed_checks"],
                item["matched"],
                item["mismatches"],
                item["unavailable"],
            ]
            for item in audit["concepts"]
        ],
    )
    lines += ["## Every country/date comparison", ""]
    lines += table(
        ["Concept", "Country", "Date", "Source", "Result", "Difference / error"],
        [
            [
                item["concept_id"],
                item["country"],
                item["date"],
                f"[{item.get('source', 'source')}]({item.get('source_url', '')})",
                item["status"],
                item.get("error") or item.get("absolute_difference"),
            ]
            for item in audit["checks"]
        ],
    )
    failures = [item for item in audit["checks"] if item["status"] != "matched"]
    lines += [
        "## Mismatches and incomplete comparisons",
        "",
        json.dumps(failures, indent=2) if failures else "None.",
        "",
    ]
    (ROOT / "docs/process/DATA_AUDIT.md").write_text("\n".join(lines).rstrip() + "\n")
    print(
        json.dumps(
            {
                "coverage": summary,
                "audit": manifest["audit_summary"],
                "fallbacks": len(fallbacks),
                "issue_counts": dict(Counter(issue["code"] for issue in read("issues.json"))),
            }
        )
    )


if __name__ == "__main__":
    main()
