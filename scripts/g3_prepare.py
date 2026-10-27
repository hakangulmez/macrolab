"""Prepare ignored, local-only browser data and verified runtime assets without networking."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from typing import Any

import yaml

from macrolab.export.script import DEPENDENCIES
from macrolab.models.registry import catalogue

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = {
    "monetary_policy": (
        "Monetary policy",
        "Compare responses to a recursive monetary-policy shock.",
    ),
    "taylor_rule": (
        "Taylor rule",
        "Estimate policy-rate associations with inflation and activity.",
    ),
    "phillips_curve": ("Phillips curve", "Examine inflation and unemployment across samples."),
    "okuns_law": ("Okun's law", "Examine output growth and unemployment changes."),
}
CATEGORIES = {
    "Real activity": {
        "gdp_real",
        "cons_priv",
        "cons_gov",
        "gfcf",
        "exports_real",
        "imports_real",
        "ind_prod",
        "retail_vol",
    },
    "Prices": {"cpi", "cpi_core", "ppi", "gdp_defl", "house_real", "ulc"},
    "Labour": {"unemp", "employment", "lfpr"},
    "Interest rates": {"policy_rate", "rate_3m", "rate_10y", "term_spread"},
    "Money and credit": {"credit_pnfs", "money_broad"},
    "Financial markets": {"equity_idx"},
    "External sector": {"reer", "neer", "fx_usd", "ca_gdp"},
    "Public finances": {"gov_debt", "gov_balance"},
    "Business cycle and confidence": {"cli", "conf_cons", "conf_bus"},
    "Global factors": {"oil_brent", "commod_idx", "us_policy_rate"},
}
SOURCES = [
    {
        "name": "OECD",
        "terms_url": "https://www.oecd.org/en/about/terms-conditions.html",
        "terms_status": "conditional; dataset and third-party restrictions apply",
        "attribution": "OECD, dataset and original provider; retain each series citation.",
    },
    {
        "name": "BIS",
        "terms_url": "https://www.bis.org/terms_conditions.htm",
        "terms_status": "conditional non-commercial use; review dataset notices",
        "attribution": "Bank for International Settlements; dataset, series and source URL.",
    },
    {
        "name": "ECB",
        "terms_url": "https://www.ecb.europa.eu/services/disclaimer/html/index.en.html",
        "terms_status": "conditional; accurate attribution and dataset exceptions apply",
        "attribution": "European Central Bank; label MacroLab transformations separately.",
    },
    {
        "name": "Eurostat",
        "terms_url": "https://ec.europa.eu/eurostat/web/main/help/copyright-notice",
        "terms_status": "conditional; attribution, modification and dataset exceptions apply",
        "attribution": "Eurostat; identify modifications and retain original-provider attribution.",
    },
    {
        "name": "IMF",
        "terms_url": "https://www.imf.org/external/terms.htm",
        "terms_status": "unresolved – no redistribution of raw data",
        "attribution": "International Monetary Fund; exact dataset terms remain unverified.",
    },
    {
        "name": "WorldBank",
        "terms_url": "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
        "terms_status": "unresolved – no redistribution of raw data",
        "attribution": (
            "World Bank, WDI or Commodity Price Data; retain underlying-provider credits."
        ),
    },
]


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n")


def prepare(root: Path = ROOT) -> dict[str, Any]:
    source = root / "data/processed/current"
    snapshot = json.loads((source / "processed_manifest.json").read_text())
    if not snapshot.get("validation_passed"):
        raise ValueError("Only a validated accepted local snapshot can prepare browser data")
    public = root / "web/public"
    data = public / "data"
    runtime = public / "runtime"
    (data / "countries").mkdir(parents=True, exist_ok=True)
    (runtime / "pyodide").mkdir(parents=True, exist_ok=True)
    countries, country_files = [], {}
    coverage: list[dict[str, Any]] = []
    for name, expected in sorted(snapshot["files"].items()):
        if not name.startswith("browser/") or not name.endswith(".json"):
            continue
        path = source / name
        if path.is_symlink() or not path.resolve().is_relative_to(
            (root / "data/processed").resolve()
        ):
            raise ValueError("Browser source must remain inside accepted processed data")
        payload = path.read_bytes()
        if digest(payload) != expected["sha256"] or len(payload) != expected["bytes"]:
            raise ValueError(f"Accepted snapshot checksum differs: {name}")
        if path.name == "global-variants.json":
            (data / path.name).write_bytes(payload)
            continue
        bundle = json.loads(payload)
        country = dict(bundle["country"])
        iso3 = country["iso3"]
        if path.stem != iso3 or bundle["snapshot_id"] != snapshot["snapshot_id"]:
            raise ValueError("Country identity does not match the accepted snapshot")
        if bundle.get("publication_approved") is not False:
            raise ValueError("Local browser bundles must retain the publication boundary")
        country["coverage_counts"] = dict(Counter(card["status"] for card in bundle["cards"]))
        latest: dict[str, Any] = {}
        for profile in bundle["profiles"]:
            key = profile["profile_id"]
            if key not in latest or profile["date"] > latest[key]["date"]:
                latest[key] = profile
        country["latest_profiles"] = list(latest.values())
        coverage.extend(
            {
                key: card.get(key)
                for key in (
                    "country",
                    "concept_id",
                    "status",
                    "first_date",
                    "last_date",
                    "reason_codes",
                    "stale",
                )
            }
            for card in bundle["cards"]
        )
        countries.append(country)
        (data / "countries" / path.name).write_bytes(payload)
        country_files[iso3] = {"url": f"/data/countries/{iso3}.json", **expected}
    if len(countries) != snapshot["countries"]:
        raise ValueError("Prepared country count differs from accepted coverage")
    definitions = yaml.safe_load((root / "configs/indicators.yaml").read_text())
    indicators = [
        {key: value for key, value in item.items() if key != "country_mappings"}
        for item in definitions["concepts"]
    ]
    for indicator in indicators:
        indicator["category"] = next(
            group for group, ids in CATEGORIES.items() if indicator["concept_id"] in ids
        )
        indicator["frequency"] = indicator["native_frequency"]
    templates = [
        {
            "id": key,
            "title": title,
            "description": description,
            "config": json.loads((root / f"configs/templates/{key}.json").read_text()),
        }
        for key, (title, description) in TEMPLATES.items()
    ]
    verification = json.loads((root / "docs/process/G2_VERIFICATION.json").read_text())
    assets = json.loads((root / "runs/g2/runtime_assets.json").read_text())
    wheel = json.loads((root / "runs/g2/runtime_wheel.json").read_text())
    for name, expected in assets["runtime_files"].items():
        payload = (root / assets["local_directory"] / name).read_bytes()
        if digest(payload) != expected["sha256"]:
            raise ValueError(f"Cached runtime checksum differs: {name}")
        (runtime / "pyodide" / name).write_bytes(payload)
    for name, expected in assets["packages"].items():
        payload = (root / assets["local_directory"] / expected["file_name"]).read_bytes()
        if digest(payload) != expected["sha256"]:
            raise ValueError(f"Cached numerical package checksum differs: {name}")
        (runtime / "pyodide" / expected["file_name"]).write_bytes(payload)
    wheel_bytes = (root / "runs/g2" / wheel["wheel_file"]).read_bytes()
    if digest(wheel_bytes) != wheel["wheel_sha256"]:
        raise ValueError("Portable source wheel checksum differs")
    (runtime / wheel["wheel_file"]).write_bytes(wheel_bytes)
    shutil.copyfile(root / "web/runtime/worker.mjs", runtime / "worker.mjs")
    shutil.copyfile(root / "web/runtime/assets.lock.json", runtime / "assets.lock.json")
    for name in ("analysis_config.schema.json", "model_result.schema.json"):
        shutil.copyfile(root / "schemas" / name, data / name)
    manifest = {
        "schema_version": 1,
        "snapshot_id": snapshot["snapshot_id"],
        "as_of_date": snapshot["as_of_date"],
        "publication_approved": False,
        "countries": sorted(countries, key=lambda item: item["name"]),
        "indicators": indicators,
        "national_concepts": snapshot["national_concepts"],
        "global_factors": snapshot["global_factors"],
        "country_files": country_files,
        "templates": templates,
        "models": catalogue(),
        "sources": SOURCES,
        "coverage_summary": snapshot["coverage_summary"],
        "coverage": coverage,
        "validation": {
            "gate": verification["gate"],
            "models": verification["model_validation"],
            "code_version": verification["code_version"],
        },
        "schema_url": "/data/analysis_config.schema.json",
        "global_variants_url": "/data/global-variants.json",
        "runtime": {
            "worker_url": "/runtime/worker.mjs",
            "index_url": "/runtime/pyodide/",
            "wheel_url": f"/runtime/{wheel['wheel_file']}",
            "wheel_sha256": wheel["wheel_sha256"],
            "code_version": wheel["code_version"],
            "asset_lock_url": "/runtime/assets.lock.json",
            "source_archive_sha256": wheel["source_archive_sha256"],
            "capabilities": ["run", "compatibility", "encode", "decode", "export"],
            "reproduction_environment": {
                "python_version": platform.python_version(),
                "dependencies": {name: version(name) for name in DEPENDENCIES},
            },
        },
    }
    write_json(data / "manifest.json", manifest)
    gate = os.environ.get("MACROLAB_REVIEW_GATE", "g4")
    if gate not in {"g3", "g31", "g4"}:
        raise ValueError("Unsupported review gate")
    write_json(
        root / "runs" / gate / "preparation.json",
        {
            "snapshot_id": snapshot["snapshot_id"],
            "countries": len(countries),
            "national_concepts": snapshot["national_concepts"],
            "global_factors": snapshot["global_factors"],
            "manifest_sha256": digest((data / "manifest.json").read_bytes()),
            "manifest_bytes": (data / "manifest.json").stat().st_size,
            "source_wheel_sha256": wheel["wheel_sha256"],
            "source_hashes": wheel["source_files"],
            "publication_approved": False,
            "network_requests": 0,
        },
    )
    return manifest


if __name__ == "__main__":
    if not (ROOT / "data/processed/current/processed_manifest.json").is_file():
        raise SystemExit(
            "Local review inputs are missing. See docs/process/LOCAL_REVIEW.md and run "
            "python3.11 scripts/seed_review_inputs.py --from /path/to/authorised/local/checkout. "
            "No data or runtime files are downloaded by this build."
        )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_runtime_assets.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    result = prepare()
    print(
        json.dumps(
            {
                "snapshot_id": result["snapshot_id"],
                "countries": len(result["countries"]),
                "indicators": result["national_concepts"],
                "global_factors": result["global_factors"],
                "manifest": "web/public/data/manifest.json",
            },
            indent=2,
        )
    )
