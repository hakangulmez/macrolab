"""Same-impulse cumulative response ratio and a joint sandwich delta interval."""

from typing import Any

import numpy as np
from scipy.stats import norm  # type: ignore[import-untyped]

from macrolab.models.base import AnalysisData
from macrolab.models.lp import _active, design


def response_ratio(data: AnalysisData, config: dict[str, Any]) -> dict[str, Any]:
    """Reuse the CPI LP design exactly, including its sample and seasonal controls.

    The impulse is 100*dlog(NEER) (or TRY/USD). Summing those changes over
    t..t+h gives the cumulative FX level target without adding any regressors.
    Joint score products retain the covariance between numerator/denominator.
    """
    d = design(data, config)
    s = d["settings"]
    if s["response_mode"] != "cumulative_log":
        return {"status": "unavailable", "reason": "Ratio requires cumulative log-level responses."}
    impulse = d["x"]["impulse"]
    direction = -1 if s["impulse"] == "neer" else 1
    rows = []
    for h, mask in enumerate(d["masks"]):
        fx = sum(impulse.shift(-j) for j in range(h + 1))
        if not np.isfinite(fx.loc[mask]).all():
            raise ValueError(
                "Cumulative FX target must cover every CPI anchor; no sample substitution"
            )
        x, _ = _active(d["x"].loc[mask])
        a = x.to_numpy()
        y = np.column_stack([d["y"].loc[mask, h], fx.loc[mask]])
        pinv = np.linalg.pinv(a, rcond=1e-15)
        beta = pinv @ y
        estimates = beta[1] * s["size"]
        score = pinv[1, :, None] * (y - a @ beta) * s["size"]
        cov = score.T @ score
        if s["covariance"] == "HC1":
            cov *= len(a) / (len(a) - np.linalg.matrix_rank(a))
        else:
            for lag in range(1, h + 2):
                cross = score[lag:].T @ score[:-lag]
                cov += (1 - lag / (h + 2)) * (cross + cross.T)
        price, exchange = map(float, estimates)
        denominator = direction * exchange
        se_exchange = float(np.sqrt(max(0, cov[1, 1])))
        weak = abs(exchange) <= norm.ppf(0.95) * se_exchange
        estimable = abs(denominator) > 1e-10
        ratio = price / denominator if estimable else None
        gradient = (
            np.array([1 / denominator, -direction * price / denominator**2]) if estimable else None
        )
        se = float(np.sqrt(max(0, gradient @ cov @ gradient))) if estimable else None
        bands = {
            str(level): {
                "lower": ratio - norm.ppf((1 + level) / 2) * se if estimable else None,
                "upper": ratio + norm.ppf((1 + level) / 2) * se if estimable else None,
            }
            for level in (0.68, 0.9)
        }
        rows.append(
            {
                "horizon": h,
                "ratio": ratio,
                "std_error": se,
                "bands": bands,
                "cpi_cumulative": price,
                "fx_cumulative": exchange,
                "fx_std_error": se_exchange,
                "depreciation_cumulative": denominator,
                "joint_covariance": cov.tolist(),
                "denominator_weak": bool(weak),
                "status": "ok" if estimable else "undefined",
                "nobs": len(a),
                "periods": [str(p) for p in x.index],
            }
        )
    return {
        "status": "ok",
        "exchange_rate": s["impulse"],
        "horizons": rows,
        "definition": (
            "Cumulative CPI response / cumulative depreciation response to the same impulse"
        ),
        "sign_convention": (
            "NEER increases with appreciation: ratio = -CPI/NEER; TRY/USD ratio = CPI/FX."
        ),
        "interval_method": (
            f"Joint {s['covariance']} sandwich delta method; pointwise normal intervals"
        ),
        "conditional": True,
        "denominator_note": (
            "Delta intervals are unreliable when the denominator is near zero; "
            "a 90% denominator interval crossing zero is flagged."
        ),
        "secondary_label": (
            "response to an initial 1% depreciation, followed by the exchange rate’s own "
            "subsequent path"
        ),
        "reference": "https://www.bankofengland.co.uk/external-mpc-discussion-paper/2017/explaining-differences-in-exchange-rate-pass-through",
    }
