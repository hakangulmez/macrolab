"""Prepare the local v2.0 release candidate from one audited, licensed snapshot."""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from p1_prepare import prepare as prepare_cleared
from p1_prepare import size_report, write_json

from macrolab.analysis.templates_v2 import catalogue as v2_templates
from macrolab.data.snapshot import sha256_file
from macrolab.models.registry import catalogue

ROOT = Path(__file__).resolve().parents[1]


def template_metadata(existing: list[dict], snapshot: str) -> list[dict]:
    """Use source-controlled catalogues; no private review folder is required."""
    entries = list(existing)
    for name, title, description in [
        (
            "same_ecb_shock",
            "Same ECB shock",
            "One EA DFR innovation, national local projections. Conditional and joint uncertainty.",
        ),
        (
            "tur_pass_through",
            "Türkiye exchange-rate pass-through",
            "Monthly prices after a 1% depreciation. Conditional association, not a causal shock.",
        ),
    ]:
        entries.append(
            dict(
                id=name,
                title=title,
                description=description,
                new_in_v1=True,
                config=json.loads((ROOT / "configs/templates" / f"{name}.json").read_text()),
            )
        )
    entries.extend(v2_templates(entries, snapshot))
    return entries


def prepare(snapshot: str, *, build: bool = False):
    marker = json.loads((ROOT / "data/manifests/refresh" / f"{snapshot}.json").read_text())
    licence = json.loads((ROOT / "docs/process/G16_LICENCE_REVIEW.json").read_text())
    if marker["status"] != "passed" or not licence["passed"]:
        raise ValueError("G16 requires a passed refresh and completed licence review")
    snapshot_manifest = json.loads(
        (ROOT / "data/processed/snapshots" / snapshot / "processed_manifest.json").read_text()
    )
    if licence["reviewed_on"] != snapshot_manifest["as_of_date"]:
        raise ValueError("Licence review must cover the selected snapshot date")
    report = prepare_cleared(candidate="g16", snapshot_id=snapshot)
    target = ROOT / "runs/g16"
    public = target / "public"
    data = public / "data"
    cards = public / "validation"
    cards.mkdir(exist_ok=True)
    for name in [
        "panel_fe",
        "panel_lp",
        "bvar_minn",
        "forecasting",
        "cointegration",
        "break-tests",
    ]:
        content = (ROOT / "docs/models" / (name + ".md")).read_text()
        page = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>MacroLab validation card</title><main>"
            '<a href="../">MacroLab</a><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'
            + html.escape(content)
            + "</pre></main></html>"
        )
        (cards / (name + ".html")).write_text(page)
    path = data / "manifest.json"
    manifest = json.loads(path.read_text())
    templates = template_metadata(manifest["templates"], snapshot)
    manifest["models"] = catalogue()
    manifest["schema_url"] = "schemas/analysis_config.schema.json"
    (public / "schemas").mkdir(exist_ok=True)
    for schema in (ROOT / "schemas").glob("*.json"):
        shutil.copy2(schema, public / "schemas" / schema.name)
    manifest["publication"].update(
        candidate="G16 v2.0 release candidate",
        included_global_factors=["oil_brent", "us_policy_rate", "commod_idx"],
        excluded_concepts=[],
        country_narratives="withheld",
    )
    manifest["templates"] = []
    for template in templates:
        config = json.loads((ROOT / "configs/templates" / f"{template['id']}.json").read_text())
        config["snapshot_id"] = snapshot
        if "first_stage" in config["model"]["params"]:
            config["model"]["params"]["first_stage"]["snapshot_id"] = snapshot
        manifest["templates"].append({**template, "config": config})
    for item in manifest["indicators"]:
        item["publication"] = {"included": True}
    variants_path = data / "global-variants.json"
    variants = json.loads(variants_path.read_text())
    for name, item in variants["variants"].items():
        observations = item["observations"]
        if not observations:
            raise ValueError(f"Required cleared variant is empty: {name}")
        item["metadata"].update(
            start=observations[0][0],
            end=observations[-1][0],
            country="EA" if name in {"dfr", "mro", "hicp_sa"} else "GLOBAL",
            status="available_note",
        )
    write_json(variants_path, variants)
    labels = {
        "all": "All commodities (IMF)",
        "energy": "Energy commodities (IMF)",
        "nonfuel": "Non-fuel commodities (IMF, default)",
        "dfr": "ECB deposit facility rate",
        "mro": "ECB main refinancing operations rate",
        "hicp_sa": "Official seasonally adjusted HICP (ECB)",
    }
    for country in manifest["countries"]:
        country_path = data / "countries" / f"{country['iso3']}.json"
        bundle = json.loads(country_path.read_text())
        assert not bundle["country"].get("notes")
        for card in bundle["cards"]:
            card["variant_options"] = [
                {"label": labels[name], **variant["metadata"]}
                for name, variant in variants["variants"].items()
                if variant["metadata"]["concept_id"] == card["concept_id"]
                and (
                    variant["metadata"]["country"] == "GLOBAL"
                    or country["iso3"] == "EA"
                    or (card["concept_id"] == "policy_rate" and country.get("policy_rate_shared"))
                )
            ]
        country["coverage_counts"] = dict(Counter(c["status"] for c in bundle["cards"]))
        write_json(country_path, bundle)
        manifest["country_files"][country["iso3"]].update(
            bytes=country_path.stat().st_size, sha256=sha256_file(country_path)
        )
    write_json(
        data / "v1-data-policy.json", json.loads((ROOT / "configs/v1_data.json").read_text())
    )
    write_json(path, manifest)
    shutil.copy2(target / "runtime-build/runtime_wheel.json", target / "runtime_wheel.json")
    wheel = json.loads((target / "runtime_wheel.json").read_text())
    shutil.copy2(target / "runtime-build" / wheel["wheel_file"], target / wheel["wheel_file"])
    if build:
        subprocess.run(
            ["npm", "run", "build", "--", "--emptyOutDir"],
            cwd=ROOT / "web",
            check=True,
            env={
                **os.environ,
                "MACROLAB_BASE_PATH": "/macrolab/",
                "MACROLAB_PUBLIC_DIR": str(public),
                "MACROLAB_BUILD_DIR": str(target / "site"),
            },
        )
    report.update(
        built=build,
        snapshot_id=snapshot,
        country_narratives="withheld",
        publication_approved=False,
        templates=[item["id"] for item in manifest["templates"]],
    )
    report["prepared_sizes"] = size_report(public, report["source_accounting"])
    write_json(target / "preparation.json", report)
    return {"snapshot_id": snapshot, "built": build, "public": str(public.relative_to(ROOT))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="20261024-2040")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.snapshot, build=args.build)))
