"""Local G5 static preview: frozen P2 observations plus separately audited v1 additions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from build_runtime_assets import build_wheel
from g5_data import load
from p1_prepare import SEGMENT_FIELDS, Policy, filter_rows, read_policy, write_json

from macrolab.data.snapshot import sha256_file

ROOT = Path(__file__).resolve().parents[1]


def prepare(root: Path = ROOT, *, build: bool = False) -> dict[str, Any]:
    addition = load(root)
    review = json.loads((root / "runs/g5/refresh.json").read_text())
    if not review["passed"]:
        raise ValueError("G5 preview requires a successful full refresh dry-run")
    snapshot = review["snapshot_id"]
    directory = root / review["manifest"]["destination"]
    target = root / "runs/g5"
    public = target / "public"
    if public.is_symlink():
        raise ValueError("G5 preview directory must not be a symlink")
    if public.exists():
        shutil.rmtree(public)
    shutil.copytree(root / "runs/p2/public", public)
    data = public / "data"
    manifest = json.loads((data / "manifest.json").read_text())
    old_snapshot = manifest["snapshot_id"]
    manifest.update(
        snapshot_id=snapshot,
        parent_snapshot_id=old_snapshot,
        global_factors=3,
        global_factors_total=3,
    )
    policy_path = root / "configs/publication_sources_v1.json"
    policy = Policy(read_policy(policy_path))
    manifest["publication"].update(
        candidate="G5 local review",
        included_global_factors=["oil_brent", "us_policy_rate", "commod_idx"],
        excluded_concepts=[],
        policy_sha256=sha256_file(policy_path),
    )
    manifest["sources"].append(
        {
            "name": "IMF PCPS",
            "terms_url": policy.by_id["imf_pcps_indices"]["terms_url"],
            "terms_status": "allowed",
            "attribution": policy.by_id["imf_pcps_indices"]["attribution"],
            "restrictions": policy.by_id["imf_pcps_indices"]["restrictions"],
        }
    )
    for template in manifest["templates"]:
        template["config"]["snapshot_id"] = snapshot
    for indicator in manifest["indicators"]:
        if indicator["concept_id"] == "commod_idx":
            indicator.update(
                title="Primary commodity price index (IMF, non-fuel)",
                source_priority=["IMF"],
                default_transform="yoy_pct",
                publication={"included": True},
            )
    commodity_cards = {}
    for country in manifest["countries"]:
        iso3 = country["iso3"]
        path = data / "countries" / f"{iso3}.json"
        bundle = json.loads(path.read_text())
        audited = json.loads((directory / "browser" / f"{iso3}.json").read_text())
        card = next(c for c in audited["cards"] if c["concept_id"] == "commod_idx")
        commodity_cards[iso3] = card
        card["publication"] = {
            "retained_observations": 417,
            "excluded_observations": 0,
            "excluded_sources": [],
            "reason": "Audited IMF PCPS non-fuel index; reviewed non-commercial terms.",
        }
        bundle["cards"] = [card if c["concept_id"] == "commod_idx" else c for c in bundle["cards"]]
        bundle["series"]["commod_idx"] = audited["series"]["commod_idx"]
        bundle.update(snapshot_id=snapshot, parent_snapshot_id=old_snapshot)
        for container in (country, bundle["country"]):
            container["coverage_counts"] = dict(Counter(c["status"] for c in bundle["cards"]))
            container["notes"] = []
        write_json(path, bundle)
        manifest["country_files"][iso3].update(bytes=path.stat().st_size, sha256=sha256_file(path))
    manifest["coverage"] = [
        commodity_cards.get(c["country"], c) if c["concept_id"] == "commod_idx" else c
        for c in manifest["coverage"]
    ]
    # Global and EA variants remain distinct, with their scope and complete source metadata.
    rows, _, _ = filter_rows(addition["variant_rows"], policy, "cleared")
    variants = {}
    for name in sorted({row["variant"] for row in rows}):
        selected = sorted([r for r in rows if r["variant"] == name], key=lambda r: r["date"])
        variants[name] = {
            "metadata": {
                k: selected[0].get(k)
                for k in (*SEGMENT_FIELDS, "country", "publication_restrictions", "terms_urls")
            },
            "observations": [
                [r["date"], r["value"], r["obs_status"], r["flags"]] for r in selected
            ],
            "publication": {"status": "retained", "reason": "G5 exact audit and reviewed terms"},
        }
        variants[name]["metadata"].update(
            start=selected[0]["date"],
            end=selected[-1]["date"],
            status="available_note",
            snapshot_as_of="2026-10-21",
            source_series_ids=sorted({r["source_series_id"] for r in selected}),
        )
    write_json(
        data / "global-variants.json",
        {"snapshot_id": snapshot, "variants": variants, "publication_approved": False},
    )
    labels = {
        "all": "All commodities (IMF)",
        "energy": "Energy commodities (IMF)",
        "nonfuel": "Non-fuel commodities (IMF, default)",
        "dfr": "ECB deposit facility rate",
        "mro": "ECB main refinancing operations rate",
        "hicp_sa": "Official seasonally adjusted HICP (ECB)",
    }
    for country in manifest["countries"]:
        path = data / "countries" / f"{country['iso3']}.json"
        bundle = json.loads(path.read_text())
        for card in bundle["cards"]:
            card["variant_options"] = [
                {"label": labels[name], **variant["metadata"]}
                for name, variant in variants.items()
                if variant["metadata"]["concept_id"] == card["concept_id"]
                and (
                    variant["metadata"]["country"] == "GLOBAL"
                    or country["iso3"] == "EA"
                    or (card["concept_id"] == "policy_rate" and country.get("policy_rate_shared"))
                )
            ]
        write_json(path, bundle)
        manifest["country_files"][country["iso3"]].update(
            bytes=path.stat().st_size, sha256=sha256_file(path)
        )
    write_json(
        data / "v1-data-policy.json", json.loads((root / "configs/v1_data.json").read_text())
    )
    wheel = build_wheel(target / "runtime-build")
    shutil.copy2(
        target / "runtime-build" / wheel["wheel_file"], public / "runtime" / wheel["wheel_file"]
    )
    manifest["runtime"].update(
        wheel_sha256=wheel["wheel_sha256"], source_archive_sha256=wheel["source_archive_sha256"]
    )
    write_json(data / "manifest.json", manifest)
    if build:
        env = os.environ.copy()
        env.update(
            MACROLAB_BASE_PATH="/macrolab/",
            MACROLAB_PUBLIC_DIR=str(public),
            MACROLAB_BUILD_DIR=str(target / "site"),
        )
        subprocess.run(["npm", "run", "build"], cwd=root / "web", env=env, check=True)
    result = {
        "snapshot_id": snapshot,
        "public": str(public.relative_to(root)),
        "built": build,
        "original_model_wheel_identical": wheel["wheel_sha256"]
        == json.loads((root / "runs/p2/public/data/manifest.json").read_text())["runtime"][
            "wheel_sha256"
        ],
        "country_narratives": "withheld",
        "publication_approved": False,
    }
    write_json(target / "preparation.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    print(json.dumps(prepare(build=parser.parse_args().build), indent=2))
