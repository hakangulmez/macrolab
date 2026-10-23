"""Refresh guards protect frozen data and reviewed source boundaries."""

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("refresh_test_module", ROOT / "scripts/refresh.py")
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


def test_revision_threshold_separates_new_removed_and_revised_periods():
    changes = refresh.changes(
        {"x": [["a", 100], ["b", 10], ["c", 4]]},
        {"x": [["a", 100.00000001], ["b", 10.1], ["d", 3]]},
    )
    assert len(changes) == 1
    assert {k: changes[0][k] for k in ("added", "removed", "revised", "above_threshold")} == {
        "added": 1,
        "removed": 1,
        "revised": 2,
        "above_threshold": 1,
    }


def test_unreviewed_flow_and_pink_sheet_block_before_network(tmp_path, monkeypatch):
    policy = refresh.Policy(refresh.read_policy(ROOT / "configs/publication_sources_v1.json"))
    client = refresh.ClearedClient(tmp_path, "20261021-0000", policy, date(2026, 10, 21))
    monkeypatch.setattr(
        refresh.SnapshotClient, "fetch", lambda *args: pytest.fail("Network reached")
    )
    for source, url in [
        ("OECD", "https://sdmx.oecd.org/public/rest/v1/data/UNREVIEWED/"),
        ("IMF", "https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS,10.0.0/"),
        ("WorldBank", "https://www.worldbank.org/en/research/commodity-markets"),
    ]:
        with pytest.raises(refresh.SnapshotError):
            client.fetch(source, "test", url, "text/csv")


def test_duplicate_snapshot_is_rejected_without_writing(tmp_path):
    marker = tmp_path / "data/manifests/refresh/20261021-0000.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"immutable":true}')
    with pytest.raises(refresh.SnapshotError, match="already exists"):
        refresh.run(tmp_path, dry_run=True, snapshot="20261021-0000", previous=tmp_path)
    assert marker.read_text() == '{"immutable":true}'


def test_pcps_policy_excludes_individual_commodity_quotes():
    policy = refresh.Policy(refresh.read_policy(ROOT / "configs/publication_sources_v1.json"))

    def row(code):
        return {
            "source": "IMF",
            "source_series_id": f"IMF.RES:PCPS(9.0.0).G001.{code}.INDEX.M",
            "source_url": "https://api.imf.org/external/sdmx/2.1/data/IMF.RES,PCPS,9.0.0/G001."
            + code
            + ".INDEX.M",
        }

    assert all(d["status"] == "allowed" for d in policy.decisions(row("PNFUEL")))
    assert all(d["status"] != "allowed" for d in policy.decisions(row("POILBRE")))


def test_seasonality_contract_requires_both_stages_and_yoy_sensitivity():
    config = json.loads((ROOT / "configs/v1_data.json").read_text())
    assert config["hicp_default_variants"]["EA"] == "hicp_sa"
    assert config["seasonality"]["year_on_year_inflation_sensitivity"] is True
    assert "both stages" in config["seasonality"]["rule"]
    assert set(config["seasonality"]["national_hicp_nsa"]) == {"DEU", "FRA", "ITA", "ESP"}


@pytest.mark.parametrize(
    "status,body,complete", [(503, b"busy", True), (200, b"", True), (200, b"partial", False)]
)
def test_live_refresh_stops_on_failed_or_incomplete_source(
    tmp_path, monkeypatch, status, body, complete
):
    policy = refresh.Policy(refresh.read_policy(ROOT / "configs/publication_sources_v1.json"))
    client = refresh.ClearedClient(tmp_path, "20261023-0000", policy, date(2026, 10, 23))
    result = SimpleNamespace(
        body=body,
        record=SimpleNamespace(status=status, body_complete=complete, error="source failure"),
    )
    monkeypatch.setattr(refresh.SnapshotClient, "fetch", lambda *args: result)
    with pytest.raises(refresh.SnapshotError, match="Source failed: BIS/test"):
        client.fetch("BIS", "test", "https://stats.bis.org/api/v1/data/WS_CBPOL/M.XM", "text/csv")


def test_strict_collection_distinguishes_source_failure_from_missing_coverage():
    from macrolab.data.pipeline import check_source_issues

    check_source_issues("OECD", [{"code": "missing_coverage"}])
    for code in ["dataset_unavailable", "source_request_unavailable", "parse_failed"]:
        with pytest.raises(refresh.SnapshotError, match="Source failed"):
            check_source_issues("OECD", [{"code": code}])


def test_refresh_comparison_bundle_includes_first_stage_and_variants(tmp_path):
    folder = tmp_path / "countries"
    folder.mkdir()
    for country in ["DEU", "EA"]:
        (folder / f"{country}.json").write_text(
            json.dumps(
                {
                    "snapshot_id": "test",
                    "as_of_date": "2026-10-23",
                    "country": {"iso3": country},
                    "cards": [{"concept_id": "gdp_real"}],
                    "series": {"gdp_real": [["2000-Q1", 100]]},
                }
            )
        )
    variants = {"dfr": {"metadata": {}, "observations": [["2000-01", 2]]}}
    (tmp_path / "global-variants.json").write_text(json.dumps({"variants": variants}))
    bundle = refresh.comparison_bundle(
        folder, {"countries": ["DEU"], "model": {"id": "cmp.common_shock"}}
    )
    assert set(bundle["countries"]) == {"DEU", "EA"}
    assert bundle["variants"]["dfr"]["metadata"] == {"start": "2000-01", "end": "2000-01"}


@pytest.mark.parametrize("status,complete", [(503, True), (200, False)])
def test_resume_rejects_prior_source_failure(tmp_path, monkeypatch, status, complete):
    marker = tmp_path / "data/manifests/refresh/test.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"status":"failed"}')
    destination = tmp_path / "data/processed/snapshots/test"
    destination.mkdir(parents=True)
    (destination / "processed_manifest.json").write_text(
        json.dumps({"validation_passed": True, "audit_summary": {"passed": True}, "files": {}})
    )
    (tmp_path / "data/manifests/raw_manifest.jsonl").write_text(
        json.dumps({"snapshot_id": "test", "status": status, "body_complete": complete}) + "\n"
    )
    monkeypatch.setattr(refresh, "verify_raw_manifest", lambda *args: None)
    with pytest.raises(refresh.SnapshotError, match="source failure"):
        refresh.resume_manifest(tmp_path, "test")


def test_resume_does_not_reopen_successful_snapshot(tmp_path):
    marker = tmp_path / "data/manifests/refresh/test.json"
    marker.parent.mkdir(parents=True)
    marker.write_text('{"status":"passed"}')
    with pytest.raises(refresh.SnapshotError, match="failed refresh marker"):
        refresh.resume_manifest(tmp_path, "test")
