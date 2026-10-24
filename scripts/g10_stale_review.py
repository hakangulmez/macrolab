"""Bounded, separate official-source review; never mutate a release snapshot."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from macrolab.data.sources.bis import read_sdmx
from macrolab.data.sources.http import SourceClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g10/stale-review"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    client = SourceClient(ROOT, "g10-stale-20261024", timeout=25, retries=0, max_bytes=16000000)
    manifest = json.loads((ROOT / "runs/v101/site/data/manifest.json").read_text())
    requests = {}
    selected = []
    for cell in manifest["coverage"]:
        if not cell.get("stale"):
            continue
        raw = json.loads(
            (ROOT / f"runs/v101/site/data/countries/{cell['country']}.json").read_text()
        )
        card = next(c for c in raw["cards"] if c["concept_id"] == cell["concept_id"])
        selected.append(
            {
                "country": cell["country"],
                "concept": cell["concept_id"],
                "last": cell["last_date"],
                "segments": card["source_segments"],
            }
        )
        for segment in card["source_segments"]:
            if segment["source"] in {"OECD", "BIS"}:
                url = segment["source_url"].split("?")[0] + "?lastNObservations=3"
                requests[url] = segment["source"]
    requests[
        "https://sdmx.oecd.org/public/rest/v1/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/GBR+ISL+TUR+USA+DEU.M.......?lastNObservations=3"
    ] = "OECD"
    requests[
        "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_inppd_m?lang=EN&freq=M&unit=I21&s_adj=NSA&indic_bt=PRC_PRR_DOM&nace_r2=C&sinceTimePeriod=2025-01"
    ] = "Eurostat"
    records = []
    for i, (url, source) in enumerate(requests.items()):
        cache = OUT / f"request-{i}.json"
        if cache.exists() and json.loads(cache.read_text()).get("status") == 200:
            records.append(json.loads(cache.read_text()))
            continue
        if cache.exists():
            (OUT / f"request-{i}-sandbox-failure.json").write_bytes(cache.read_bytes())
        fetched = client.fetch(
            source, f"stale-{i}", url, "text/csv" if source != "Eurostat" else "application/json"
        )
        record = asdict(fetched.record)
        if fetched.record.status == 200 and fetched.body:
            if source != "Eurostat":
                rows, _ = read_sdmx(fetched.body)
                (OUT / f"rows-{i}.json").write_text(json.dumps(rows) + "\n")
                record["parsed_rows"] = len(rows)
            else:
                data = json.loads(fetched.body)
                (OUT / f"rows-{i}.json").write_text(json.dumps(data) + "\n")
                record["dimensions"] = data.get("id")
        cache.write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
        print(
            source, i, record["status"], record.get("parsed_rows"), record.get("error"), flush=True
        )
    (OUT / "review-inputs.json").write_text(
        json.dumps(
            {"cells": selected, "requests": records, "release_data_changed": False}, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
