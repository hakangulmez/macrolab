"""Independently query three PPI countries; propose, never activate, replacements."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from macrolab.data.sources.eurostat import jsonstat_observations
from macrolab.data.sources.http import SourceClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs/g10/stale-review"


def main():
    bulk = jsonstat_observations(json.loads((OUT / "rows-4.json").read_text()))
    client = SourceClient(ROOT, "g10-audit-20261024", timeout=25, retries=0)
    checks = []
    candidates = []
    for geo, country in [("NO", "NOR"), ("CH", "CHE"), ("TR", "TUR")]:
        url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_inppd_m?lang=EN&freq=M&unit=I21&s_adj=NSA&indic_bt=PRC_PRR_DOM&nace_r2=C&geo={geo}&sinceTimePeriod=1998-01"
        cache = OUT / f"audit-{geo}.json"
        if cache.exists():
            metadata = json.loads(cache.read_text())
            body = (ROOT / metadata["raw_path"]).read_bytes()
        else:
            result = client.fetch("Eurostat", "ppi-" + geo, url, "application/json")
            metadata = asdict(result.record)
            body = result.body
            assert metadata["status"] == 200 and body, metadata
            cache.write_text(json.dumps(metadata, indent=2) + "\n")
        raw = json.loads(body)
        # Independent direct coordinate indexing for a singleton-country query.
        values = raw["value"]
        times = raw["dimension"]["time"]["category"]["index"]
        assert raw["size"][:-1] == [1] * 6
        available = [
            date
            for date, index in times.items()
            if str(index) in values and values[str(index)] is not None
        ]
        for date in ["2025-01", "2025-11", "2026-09"]:
            parsed = next(v for _, s, v, _ in bulk if s["geo"] == geo and s["time"] == date)
            official = float(values[str(times[date])])
            assert parsed == official
            checks.append(
                {"country": country, "date": date, "difference": parsed - official, "passed": True}
            )
        candidates.append(
            {
                "country": country,
                "concept_id": "ppi",
                "source": "Eurostat",
                "dataset": "sts_inppd_m",
                "geo": geo,
                "freq": "M",
                "unit": "I21",
                "sa_flag": "NSA",
                "activity": "C",
                "market": "domestic",
                "indic_bt": "PRC_PRR_DOM",
                "start": min(available),
                "end": max(available),
                "source_url": url,
                "apply_at": "G16 approved refresh only",
                "definition_note": (
                    "Domestic manufacturing producer prices, 2021=100, NSA. "
                    "Replace the history as a separate source series; never splice index bases."
                ),
            }
        )
    report = {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "replacement_candidates": candidates,
        "release_data_changed": False,
    }
    (OUT / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    (ROOT / "configs/g16_stale_candidates.json").write_text(
        json.dumps(
            {
                "active": False,
                "candidates": candidates,
                "audit": "docs/process/G10_STALE_REVIEW.md",
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
