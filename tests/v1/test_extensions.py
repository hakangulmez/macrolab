from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from macrolab.analysis.engine import run_analysis
from macrolab.analysis.seasonality import with_seasonal_controls
from macrolab.compare.common_shock import compare_countries, method_comparison
from macrolab.ident.bootstrap import CancelledError, joint_bootstrap
from macrolab.ident.external_series import attach, recover
from macrolab.models.lp import fit
from macrolab.outputs.hd import decompose
from tests.v1.fixtures import common_case, two_stage


def test_hd_hand_computed_fixture_and_identity():
    # y[t]=diag(.5,.25)y[t-1]+e[t], initial=[2,4], constant=[1,-1].
    y = np.array([[2.0, 4.0], [3.0, 2.0], [2.5, -0.5]])
    fake = SimpleNamespace(
        coefs=np.array([np.diag([0.5, 0.25])]),
        endog=y,
        k_ar=1,
        neqs=2,
        sigma_u=np.eye(2),
        resid=np.array([[1.0, 2.0], [0.0, 0.0]]),
        endog_lagged=np.ones((2, 1)),
        k_exog=1,
        params=np.array([[1.0, -1.0]]),
        names=["a", "b"],
    )
    result = decompose(fake, ["0", "1", "2"])
    np.testing.assert_allclose(
        result["initial_condition"], [[2, 4], [1, 1], [0.5, 0.25]], atol=1e-14
    )
    np.testing.assert_allclose(result["deterministic"], [[0, 0], [1, -1], [1.5, -1.25]], atol=1e-14)
    np.testing.assert_allclose(result["contributions"][2], [[0.5, 0], [0, 0.5]], atol=1e-14)
    assert result["maximum_identity_error"] < 1e-14
    fake.coefs[0, 0, 0] = 1.1
    with pytest.raises(ValueError, match="stable"):
        decompose(fake, ["0", "1", "2"])


def test_fitted_hd_exact_shock_reconstruction_and_alignment_failures():
    first, config, country, _ = two_stage()
    shock, fitted = recover(first, config)
    hd = decompose(fitted, list(first.frame.index))
    assert hd["maximum_identity_error"] < 1e-12
    impact = np.linalg.cholesky(fitted.sigma_u)
    np.testing.assert_allclose(np.array(shock["all_values"]) @ impact.T, fitted.resid, atol=1e-12)
    attached = attach(country, shock)
    assert len(attached.frame) == len(country.frame)
    for change in ["missing", "duplicate", "frequency"]:
        altered = deepcopy(shock)
        if change == "missing":
            altered["periods"], altered["values"] = altered["periods"][1:], altered["values"][1:]
        elif change == "duplicate":
            altered["periods"][1] = altered["periods"][0]
        else:
            altered["frequency"] = "M"
        with pytest.raises(ValueError):
            attach(country, altered)


def test_one_country_comparison_identical_and_cancel():
    first, fc, country, config = two_stage()
    shock, _ = recover(first, fc)
    expected = fit(attach(country, shock), config)
    progress = []
    comparison = compare_countries(
        shock, {"AAA": country}, {"AAA": config}, progress=progress.append
    )
    assert comparison["entries"][0]["result"] == expected
    assert progress[-1]["completed"] == 1
    with pytest.raises(CancelledError):
        compare_countries(shock, {"AAA": country}, {"AAA": config}, cancelled=lambda: True)
    row = method_comparison(expected, expected, same_estimand=False)
    assert not row["include_in_agreement_counts"]
    assert row["label"] == "different method and different identification"


def test_joint_bootstrap_seed_controls_default_and_unbalanced_block():
    first, fc, country, config = two_stage(100)
    first.metadata["x"] = {"sa_flag": "NSA"}
    country.metadata["y"] = {"sa_flag": "NSA"}
    assert with_seasonal_controls(first, fc).exog.shape[1] == 3
    assert with_seasonal_controls(country, config).exog.shape[1] == 3
    a = joint_bootstrap(first, fc, {"AAA": country}, {"AAA": config}, draws=20, seed=17)
    b = joint_bootstrap(first, fc, {"AAA": country}, {"AAA": config}, draws=20, seed=17)
    assert a == b and not a["default_enabled"]
    assert a["attempts"] == a["draws"] + a["failed_draws"]
    shorter = deepcopy(country)
    shorter.frame = shorter.frame.iloc[1:]
    with pytest.raises(ValueError, match="common-window"):
        joint_bootstrap(
            first, fc, {"AAA": country, "BBB": shorter}, {"AAA": config, "BBB": config}, draws=20
        )
    with pytest.raises(CancelledError):
        joint_bootstrap(
            first, fc, {"AAA": country}, {"AAA": config}, draws=20, cancelled=lambda: True
        )


def test_common_engine_off_by_default_and_euro_adoption():
    config, bundle = common_case()
    bundle["countries"]["AAA"]["metadata"]["euro_adoption"] = "2005-01-01"
    result = run_analysis(config, bundle)
    assert result["status"] == "ok", result["checks"]
    assert result["joint_bootstrap"]["status"] == "disabled"
    assert result["results"][0]["actual_sample"]["start"] >= "2005"
    assert any(c["code"] == "euro_sample_start" for c in result["checks"])
    config["model"]["params"].update(joint_bootstrap=True, bootstrap_draws=20)
    result = run_analysis(config, bundle)
    assert result["joint_bootstrap"]["status"] == "ok", result["joint_bootstrap"]


def test_multiresponse_comparison_keeps_separate_results_and_samples():
    config, bundle = common_case()
    source = bundle["countries"]["AAA"]["series"]["y"]
    extra = deepcopy(source)
    extra["metadata"]["concept_id"] = "w"
    rng = np.random.default_rng(889)
    extra["observations"] = [
        [p, 0.7 * y + noise]
        for (p, y), noise in zip(
            source["observations"], rng.normal(size=len(source["observations"])), strict=True
        )
    ]
    bundle["countries"]["AAA"]["series"]["w"] = extra
    config["series"].append({"concept_id": "w", "role": "response", "transform": "level"})
    result = run_analysis(config, bundle)
    assert result["status"] == "ok"
    assert set(result["results"][0]["response_results"]) == {"y", "w"}
    assert len(result["common_shock"]["summary"]) == 2
    assert set(result["actual_samples"]["AAA"]["responses"]) == {"y", "w"}


def test_v1_numeric_config_canonicalisation_survives_javascript_json():
    from macrolab.analysis.config import config_hash, validated_config

    config, _ = common_case()

    def javascript_numbers(v):
        if isinstance(v, dict):
            return {k: javascript_numbers(x) for k, x in v.items()}
        if isinstance(v, list):
            return [javascript_numbers(x) for x in v]
        return int(v) if isinstance(v, float) and v.is_integer() else v

    assert config_hash(validated_config(config)) == config_hash(
        validated_config(javascript_numbers(config))
    )


def test_stage_one_internal_calendar_gap_blocks():
    first, config, _, _ = two_stage()
    first.frame = first.frame.drop(first.frame.index[50])
    with pytest.raises(ValueError, match="regular calendar"):
        recover(first, config)


def test_common_engine_blocks_uncovered_national_dates_until_explicit_restriction():
    config, bundle = common_case()
    last_covered = bundle["countries"]["EA"]["series"]["x"]["observations"][-10][0]
    config["model"]["params"]["first_stage"]["sample"]["end"] = last_covered
    blocked = run_analysis(config, bundle)
    assert blocked["status"] == "blocked"
    assert any(c["code"] == "shock_alignment" for c in blocked["checks"])
    assert not blocked["results"][0]["actual_sample"]["estimation_performed"]
    config["sample"]["end"] = last_covered
    assert run_analysis(config, bundle)["status"] == "ok"


def test_multiresponse_common_engine_returns_blocked_first_stage_without_exception():
    config, bundle = common_case()
    config["series"].append({"concept_id": "w", "role": "response", "transform": "level"})
    bundle["countries"]["AAA"]["series"]["w"] = deepcopy(bundle["countries"]["AAA"]["series"]["y"])
    bundle["countries"]["EA"]["series"]["policy"]["metadata"]["status"] = "missing"
    blocked = run_analysis(config, bundle)
    assert blocked["status"] == "blocked"
    assert blocked["common_shock"]["summary"] == []
