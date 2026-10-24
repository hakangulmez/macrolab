"""Hansen fixed-regressor wild bootstrap; vectorised draws, no extra dependencies."""

from typing import Any

import numpy as np

from macrolab.models.forecast_common import Cancelled, Progress, tick


def designs(x: np.ndarray[Any, Any], tested: list[int]) -> list[dict[str, Any]]:
    n, k = x.shape
    q = len(tested)
    x = x.copy()
    x[:, tested] = np.linalg.qr(x[:, tested], mode="reduced")[0] * np.sqrt(n)
    out = []
    for split in range(int(np.ceil(0.15 * n)), int(np.floor(0.85 * n)) + 1):
        changed = x[:, tested].copy()
        changed[:split] = 0
        a = np.column_stack([x, changed])
        if split <= q or n - split <= q or n <= k + q or np.linalg.matrix_rank(a) != k + q:
            continue
        pinv = np.linalg.pinv(a)
        influence = pinv[-q:]
        out.append(
            dict(
                split=split,
                a=a,
                pinv=pinv,
                influence=influence,
                bread=influence @ influence.T,
                df=n - k - q,
            )
        )
    if not out:
        raise ValueError("No estimable break dates inside the 15%-trimmed window.")
    return out


def statistics(
    y: np.ndarray[Any, Any], design: dict[str, Any], bandwidth: int
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Rows are original data or bootstrap draws; outputs are Wald/q."""
    a, pinv, influence = design["a"], design["pinv"], design["influence"]
    q = influence.shape[0]
    coeff = y @ pinv.T
    errors = y - coeff @ a.T
    delta = coeff[:, -q:]
    sse = np.sum(errors**2, axis=1)
    conventional = np.sum(delta * np.linalg.solve(design["bread"], delta.T).T, axis=1)
    conventional /= q * sse / design["df"]
    if q > 3:
        # Contract over time with matrix multiplication rather than allocating
        # draw × time × coefficient score tensors for larger equations.
        weights = np.einsum("it,jt->tij", influence, influence).reshape(errors.shape[1], -1)
        covariance = (errors**2) @ weights
        for lag in range(1, bandwidth + 1):
            cross = np.einsum("it,jt->tij", influence[:, lag:], influence[:, :-lag])
            weights = (cross + cross.transpose(0, 2, 1)).reshape(errors.shape[1] - lag, -1)
            covariance += (
                (1 - lag / (bandwidth + 1)) * (errors[:, lag:] * errors[:, :-lag]) @ weights
            )
        cov = covariance.reshape(-1, q, q)
    else:
        scores = errors[:, :, None] * influence.T[None, :, :]
        cov = np.einsum("bti,btj->bij", scores, scores)
        for lag in range(1, bandwidth + 1):
            cross = np.einsum("bti,btj->bij", scores[:, lag:], scores[:, :-lag])
            cov += (1 - lag / (bandwidth + 1)) * (cross + cross.transpose(0, 2, 1))
    hac = np.sum(delta * np.linalg.solve(cov, delta[..., None])[..., 0], axis=1) / q
    return conventional, hac, sse


def calibrate(
    y: np.ndarray[Any, Any],
    x: np.ndarray[Any, Any],
    tested: list[int],
    bandwidth: int = 4,
    draws: int = 499,
    seed: int = 42,
    *,
    progress: Progress = None,
    cancelled: Cancelled = None,
) -> dict[str, Any]:
    prepared = designs(x, tested)
    observed = [statistics(y[None, :], d, bandwidth) for d in prepared]
    # Hansen (2000), section 2: unrestricted residuals at the minimum-SSE split.
    best = int(np.argmin([r[2][0] for r in observed]))
    d = prepared[best]
    residual = y - d["a"] @ (d["pinv"] @ y)
    generated = np.random.default_rng(seed).normal(size=(draws, len(y))) * residual
    maxima = np.full((2, draws), -np.inf)
    for i, design in enumerate(prepared):
        tick(progress, cancelled, "break_bootstrap", i, len(prepared))
        conventional, hac, _ = statistics(generated, design, bandwidth)
        maxima[0] = np.maximum(maxima[0], conventional)
        maxima[1] = np.maximum(maxima[1], hac)
    tick(progress, cancelled, "break_bootstrap", len(prepared), len(prepared))
    result: dict[str, Any] = dict(
        draws=draws,
        seed=seed,
        residual_split=int(d["split"]),
        method="Hansen (2000) fixed-regressor Gaussian wild bootstrap",
        residuals="Unrestricted minimum-SSE break fit; regressors held fixed",
        p_value_rule="(1 + draws at least as large as observed) / (draws + 1)",
        serial_correlation_note=(
            "IID multipliers do not preserve serial correlation; "
            "HAC studentisation does not change this limitation."
        ),
    )
    for j, key in enumerate(["hc_bootstrap", "hac_bootstrap"]):
        observed_max = max(float(r[j][0]) for r in observed)
        result[key] = dict(
            statistic=observed_max,
            p_value=float((1 + np.count_nonzero(maxima[j] >= observed_max)) / (draws + 1)),
            critical_values=dict(
                zip(
                    ["90", "95", "99"],
                    np.quantile(maxima[j], [0.9, 0.95, 0.99]).tolist(),
                    strict=True,
                )
            ),
        )
    result["observed_path"] = [
        dict(split=d["split"], conventional=float(r[0][0]), hac=float(r[1][0]))
        for d, r in zip(prepared, observed, strict=True)
    ]
    return result
