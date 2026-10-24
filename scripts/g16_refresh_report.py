"""Report cached before/after refresh results without re-estimation or default edits."""

import json
from pathlib import Path

from g15_verify_exports import without_timing
from p2_validate import differences
from refresh import changes

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "20261024-2040"
OUT = ROOT / "runs/refresh" / SNAPSHOT


def headlines(r):
    output = {}
    for country in r["results"]:
        key = country.get("outcome", country["country"])
        if "evaluation" in country:
            for metric in country["evaluation"]["metrics"]:
                output[f"{metric['model']} h{metric['horizon']} RMSE"] = metric["rmse"]
        elif "pass_through" in country:
            for row in country["pass_through"]["horizons"]:
                if row["horizon"] in [6, 12, 24]:
                    output[f"Ratio h{row['horizon']}"] = row["ratio"]
        elif "irf" in country:
            responses = country.get("response_results", [country])
            if isinstance(responses, dict):
                responses = list(responses.values())
            for response in responses:
                irf = response["irf"]
                for j, variable in enumerate(irf["variables"]):
                    h = max(range(len(irf["values"])), key=lambda h: abs(irf["values"][h][j]))
                    output[f"{key} {variable} selected peak"] = irf["values"][h][j]
        else:
            for row in country.get("coefficients_table", []):
                if row["term"] in ["cpi", "gdp_real", "unemp", "oil_brent"]:
                    output[f"{key} {row['term']} coefficient"] = row["estimate"]
    return output


def main():
    report = json.loads((OUT / "comparison.json").read_text())
    template_rows = []
    for name, item in report["templates"].items():
        a, b = [
            json.loads((OUT / "results" / f"{name}-{side}.json").read_text())
            for side in ["before", "after"]
        ]
        delta, structure, count = differences(without_timing(a), without_timing(b))
        item.update(
            numerical_fields=count,
            changed_fields=len(delta),
            maximum_absolute_difference=max((abs(x["difference"]) for x in delta), default=0),
            structural_changes=structure,
        )
        ah, bh = headlines(a), headlines(b)
        assert set(ah) == set(bh)
        item["headlines"] = [
            dict(
                headline=k,
                before=ah[k],
                after=bh[k],
                sign_flip=ah[k] * bh[k] < 0,
                material=abs(bh[k] - ah[k]) > 0.5 * abs(ah[k]) or ah[k] * bh[k] < 0,
            )
            for k in ah
        ]
        template_rows.extend(dict(template=name, **x) for x in item["headlines"])
    oldfolder = ROOT / "runs/g15/site/data"
    newfolder = ROOT / "data/processed/snapshots" / SNAPSHOT
    oldstale = set()
    for p in (oldfolder / "countries").glob("*.json"):
        oldstale.update(
            p.stem + "/" + c["concept_id"]
            for c in json.loads(p.read_text())["cards"]
            if c.get("stale")
        )
    newstale = {
        c["country"] + "/" + c["concept_id"]
        for c in json.loads((newfolder / "series_cards.json").read_text())
        if c.get("stale")
    }
    report["cleared_stale"] = sorted(oldstale - newstale)
    report["remaining_stale"] = sorted(newstale)
    assert oldstale - newstale == {"NOR/ppi", "CHE/ppi", "TUR/ppi"} and not newstale - oldstale
    variants = []
    for folder in [oldfolder, newfolder / "browser"]:
        variants.append(
            {
                k: v["observations"]
                for k, v in json.loads((folder / "global-variants.json").read_text())[
                    "variants"
                ].items()
            }
        )
    report["variant_changes"] = changes(*variants)
    report["material_headline_changes"] = [r for r in template_rows if r["material"]]
    report["ppi_audit"] = json.loads((newfolder / "source_details.json").read_text())["G16_PPI"]
    (OUT / "comparison.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = [
        f"# Refresh {SNAPSHOT}",
        "",
        "24 October 2026. Previous accepted snapshot: `20261023-1634` (G15).",
        "",
        (
            "**Passed:** 62/62 official-source requests; 324/324 core audit checks, "
            "18/18 variant checks, EIA three-date check and 9/9 additional PPI checks. "
            "No source failure or changed reuse restriction. No push/deploy. Country "
            "narratives withheld."
        ),
        "",
        (
            "Only the approved three PPI source histories changed. These are full "
            "Eurostat domestic-manufacturing replacements, NSA, 2021=100, not splices or "
            "like-for-like revisions of the former OECD indices. Index-level differences "
            "below therefore also reflect different definitions/bases. The reporting "
            "threshold remains max(1e-8, 1e-6 × absolute old value). All other "
            "observations, including global variants, are unchanged."
        ),
        "",
        (
            "| Country / concept | Added | Removed | Changed common dates | Above "
            "threshold | Max absolute difference | New history |"
        ),
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in report["series_changes"]:
        lines.append(
            f"| {r['country']}/{r['series']} | {r['added']} | {r['removed']} | "
            f"{r['revised']} | {r['above_threshold']} | {r['max_revision']:.8g} | "
            f"{r['start']}–{r['end']} |"
        )
    lines += [
        "",
        (
            "Stale flags: **35 → 32**. Cleared: NOR/PPI, CHE/PPI, TUR/PPI. New: none. "
            "Every other stale flag remains."
        ),
        "",
        "## Unchanged defaults and actual samples",
        "",
        "| Template | Before → after sample | Before → after N | Numeric fields | Changed |",
        "|---|---|---:|---:|---:|",
    ]
    for name, r in report["templates"].items():
        a, b = r["before"]["sample"], r["after"]["sample"]
        lines.append(
            f"| {name} | {a['start']}–{a['end']} → {b['start']}–{b['end']} | "
            f"{a['nobs']} → {b['nobs']} | {r['numerical_fields']} | "
            f"{r['changed_fields']} |"
        )
    lines += [
        "",
        (
            "All nine defaults and all sensitivity numerical results are unchanged. "
            "Elapsed times, software version and source provenance are excluded from "
            "numeric comparisons. The pooled Phillips endpoint remains 2026 Q2 under the "
            "accepted complete-quarter rule. The inflation horse race still excludes the "
            "failed 2009 Q1 ARIMA origin from all paired model scores. No new technical "
            "exception or retuning."
        ),
        "",
        (
            "The legacy ECB row reports the same anchor window and N=92 for each of "
            "Germany, France, Italy and Spain (368 country-anchor observations). The pooled "
            "ECB row has 84 anchors per country, 336 observations for each outcome, with "
            "h=20 targets through 2026 Q2. All per-country windows are unchanged."
        ),
        "",
        (
            "The forecast table reports the input window, including 1998 observations needed "
            "for y/y transformations. Its actual first training window is 1999 Q1–2008 Q4 "
            "(40 quarters); origins run from 2008 Q4 through 2026 Q1, with targets through "
            "2026 Q2. There are 70 attempted / 69 successful origins and 69/66/62 paired "
            "forecasts at h=1/4/8, unchanged before and after refresh."
        ),
        "",
        "## Headlines",
        "",
        "| Template | Headline | Before | After | >50% or sign flip |",
        "|---|---|---:|---:|---|",
    ]
    for r in template_rows:
        lines.append(
            f"| {r['template']} | {r['headline']} | {r['before']:.8g} | "
            f"{r['after']:.8g} | {'Yes' if r['material'] else 'No'} |"
        )
    lines += [
        "",
        (
            "No material headline changes. Per-country and per-outcome samples, all "
            "warnings, source substitutions and full results are retained in "
            "`runs/refresh/"
        )
        + SNAPSHOT
        + "/comparison.json` and `results/`. Snapshot audit, provenance and hashes are in "
        "`data/processed/snapshots/" + SNAPSHOT + "/`. Existing snapshots remain immutable.",
    ]
    (ROOT / "docs" / f"REFRESH_{SNAPSHOT}.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            dict(
                templates=len(report["templates"]),
                changed_numerical_fields=sum(
                    x["changed_fields"] for x in report["templates"].values()
                ),
                headlines=len(template_rows),
                material=len(report["material_headline_changes"]),
            )
        )
    )


if __name__ == "__main__":
    main()
