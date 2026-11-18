"""Prepare static, attributed evidence shards; never regenerate timeline notes or embeddings."""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"statement", "minutes", "beige_book", "sloos"}
DISTRICTS = {
    "Boston",
    "New York",
    "Philadelphia",
    "Cleveland",
    "Richmond",
    "Atlanta",
    "Chicago",
    "St. Louis",
    "Minneapolis",
    "Kansas City",
    "Dallas",
    "San Francisco",
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def loadl(p):
    return [json.loads(line) for line in p.open()]


def build(archive: Path, audit: Path, out: Path, record: Path):
    docs = {d["document_id"]: d for d in loadl(archive / "documents.jsonl")}
    quarantine = set(json.loads(audit.read_text())["quarantine_chunk_ids"])
    countries_data = json.loads((ROOT / "web/src/data/report-timeline-countries.json").read_text())
    countries = [
        {"id": k, "name": v}
        for k, v in {
            "USA": "United States",
            "EA": "Euro area",
            "TUR": "Türkiye",
            "AUS": "Australia",
            "AUT": "Austria",
            "BEL": "Belgium",
            "CAN": "Canada",
            "CHL": "Chile",
            "COL": "Colombia",
            "CRI": "Costa Rica",
            "CZE": "Czechia",
            "DNK": "Denmark",
            "EST": "Estonia",
            "FIN": "Finland",
            "FRA": "France",
            "DEU": "Germany",
            "GRC": "Greece",
            "HUN": "Hungary",
            "ISL": "Iceland",
            "IRL": "Ireland",
            "ISR": "Israel",
            "ITA": "Italy",
            "JPN": "Japan",
            "KOR": "Korea",
            "LVA": "Latvia",
            "LTU": "Lithuania",
            "LUX": "Luxembourg",
            "MEX": "Mexico",
            "NLD": "Netherlands",
            "NZL": "New Zealand",
            "NOR": "Norway",
            "POL": "Poland",
            "PRT": "Portugal",
            "SVK": "Slovak Republic",
            "SVN": "Slovenia",
            "ESP": "Spain",
            "SWE": "Sweden",
            "CHE": "Switzerland",
            "GBR": "United Kingdom",
        }.items()
    ]
    assert set(countries_data["coverage"]["countries"]) == {c["id"] for c in countries}
    groups = collections.defaultdict(list)
    source_hashes = {}
    counts = collections.Counter()
    aliases = {}
    for c in loadl(archive / "chunks.jsonl"):
        d = docs[c["document_id"]]
        if (
            d["institution"] != "Fed"
            or d["kind"] not in KINDS
            or not d.get("published_at")
            or d.get("date_precision") not in {"day", "minute"}
            or c["chunk_id"] in quarantine
        ):
            continue
        assert hashlib.sha256(c["text"].encode()).hexdigest() == c["chunk_text_sha256"]
        date = d["published_at"][:10]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)
        assert d["rights_status"] == "fed_board_public_domain_with_attribution"
        p = {
            "id": "fed:" + c["chunk_id"],
            "sourceIds": [c["chunk_id"]],
            "noteIds": [],
            "text": c["text"],
            "country": "USA",
            "institution": "Fed",
            "title": d["title"],
            "kind": d["kind"],
            "publishedOn": date,
            "eventOn": d.get("event_date"),
            "url": c["source_url"],
            "section": c.get("section"),
            "speaker": c.get("speaker"),
            "region": c["section"] if c.get("section") in DISTRICTS else None,
            "scope": "regional" if c.get("section") in DISTRICTS else "report_context",
            "sourceType": "report",
            "discovery": "",
        }
        groups[date[:4]].append(p)
        aliases[c["chunk_id"]] = p
        counts[d["kind"]] += 1
        source_hashes[d["document_id"]] = d["source_sha256"]
    assert sum(counts.values()) == 8581, counts
    timeline = []
    old = []
    for name in ["pilot", "reviewed", "regions", "countries"]:
        path = ROOT / "web/src/data" / f"report-timeline-{name}.json"
        old.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path)})
        for note in json.loads(path.read_text())["notes"]:
            for i, part in enumerate(note["source"].get("passages") or [note["source"]]):
                p = {
                    "id": f"timeline:{note['id']}:{i}",
                    "sourceIds": [part["chunkId"]],
                    "noteIds": [note["id"]],
                    "text": part["quote"],
                    "country": note["country"],
                    "institution": note["source"]["institution"],
                    "title": note["source"]["title"],
                    "kind": docs.get(note["source"]["documentId"], {}).get(
                        "kind",
                        "outlook" if note["source"]["institution"] == "OECD" else "policy_release",
                    ),
                    "publishedOn": note["publishedOn"],
                    "eventOn": note.get("eventOn"),
                    "url": part["url"],
                    "section": part.get("section"),
                    "speaker": None,
                    "region": None,
                    "scope": "country_report",
                    "sourceType": "timeline",
                    "discovery": (
                        f"{note['title']} {note['summary']} "
                        f"{' '.join(note['topics'])} {note['kind']}"
                    ),
                }
                timeline.append(p)
    assert len(timeline) == 809
    # Preserve the quote records separately. Source aliases allow the evaluator to
    # accept a larger, source-verbatim report passage containing the same quote.
    groups["timeline"] = timeline
    out.mkdir(parents=True, exist_ok=False)
    shards = []
    for key, passages in sorted(groups.items()):
        raw = (
            json.dumps({"passages": passages}, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()
        packed = gzip.compress(raw, mtime=0)
        name = f"{key}.json.gz"
        (out / name).write_bytes(packed)
        shards.append(
            {
                "key": key,
                "file": name,
                "passages": len(passages),
                "bytes": len(packed),
                "sha256": hashlib.sha256(packed).hexdigest(),
                "rawBytes": len(raw),
            }
        )
    manifest = {
        "schemaVersion": 1,
        "asOf": "2026-11-17",
        "timelineNotes": 801,
        "timelinePassages": 809,
        "reportPassages": 8581,
        "reportDocuments": len(source_hashes),
        "excludedChunks": len(quarantine),
        "institutions": sorted({p["institution"] for values in groups.values() for p in values}),
        "countries": countries,
        "shards": shards,
        "scope": (
            "Selected timeline quotations and date-verified Fed statements, minutes, "
            "Beige Book summaries and SLOOS prose; not a complete international report archive."
        ),
        "historicalVintagesVerified": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    record.write_text(
        json.dumps(
            {
                "manifest": manifest,
                "timelineFiles": old,
                "archiveManifestSha256": sha(archive / "documents.jsonl"),
                "chunkFileSha256": sha(archive / "chunks.jsonl"),
                "auditSha256": sha(audit),
                "sourceHashes": source_hashes,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "notes": 801,
                "passages": sum(s["passages"] for s in shards),
                "reportDocuments": len(source_hashes),
                "compressedBytes": sum(s["bytes"] for s in shards),
                "shards": len(shards),
            }
        )
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--archive", type=Path, required=True)
    a.add_argument("--audit", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--record", type=Path, required=True)
    v = a.parse_args()
    build(v.archive, v.audit, v.out, v.record)
