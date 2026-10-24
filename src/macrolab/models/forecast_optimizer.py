"""Portable BFGS for the new SARIMAX likelihood only.

Explicit scalar operation order and integer line-search coordinates avoid
native/WASM BLAS/FMA branch differences. Search coordinates use a 1e-10 grid,
normalized objective 1e-8, gradient 1e-9, and inverse Hessian ten significant
digits. Reported likelihoods and predictions are not rounded.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np


def quantize(value: float, decimals: int) -> float:
    """Nearest grid point with an explicit, platform-independent half-tie rule."""
    scale = 10.0**decimals
    z = abs(value) * scale
    base = math.floor(z)
    fraction = z - base
    # A small tolerance around ties absorbs last-bit math-library differences.
    tie = abs(fraction - 0.5) <= max(1e-4, 64 * math.ulp(z))
    return math.copysign((base + int(fraction > 0.5 or tie)) / scale, value)


def dot(a: list[float], b: list[float]) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def portable_bfgs(
    fun: Callable[[Any], float], jac: Callable[[Any], Any], initial: Any
) -> dict[str, Any]:
    x = [quantize(float(v), 10) for v in initial]
    n = len(x)
    h = [[float(i == j) for j in range(n)] for i in range(n)]
    value = quantize(float(fun(np.array(x))), 8)
    gradient = [quantize(float(v), 9) for v in jac(np.array(x))]
    for iteration in range(250):
        if max(map(abs, gradient)) <= 2e-9:
            return {"x": np.array(x), "converged": True, "iterations": iteration}
        direction = [quantize(-dot(row, gradient), 10) for row in h]
        if dot(gradient, direction) >= 0:
            h = [[float(i == j) for j in range(n)] for i in range(n)]
            direction = [-v for v in gradient]
        size = max(map(abs, direction))
        if size > 5:
            direction = [quantize(v * (5 / size), 10) for v in direction]
        slope = quantize(dot(gradient, direction), 10)
        accepted = False
        for power in range(35):
            step = 2.0 ** (-power)
            increments = []
            for v in direction:
                integer = int(round(v * 1e10))
                rounded = (
                    integer
                    if power == 0
                    else (1 if integer >= 0 else -1)
                    * ((abs(integer) + 2 ** (power - 1)) // 2**power)
                )
                increments.append(rounded)
            candidate = [
                (int(round(a * 1e10)) + b) / 1e10 for a, b in zip(x, increments, strict=True)
            ]
            if candidate == x:
                break
            raw_value = float(fun(np.array(candidate)))
            if not math.isfinite(raw_value):
                continue
            trial = quantize(raw_value, 8)
            threshold = quantize(value + 1e-4 * step * slope, 8)
            if trial <= threshold:
                raw_gradient = jac(np.array(candidate))
                if np.isfinite(raw_gradient).all():
                    new_gradient = [quantize(float(v), 9) for v in raw_gradient]
                    accepted = True
                    break
        if not accepted:
            break
        displacement = [a - b for a, b in zip(candidate, x, strict=True)]
        change = [a - b for a, b in zip(new_gradient, gradient, strict=True)]
        curvature = quantize(dot(change, displacement), 14)
        if curvature > 1e-14:
            hy = [dot(row, change) for row in h]
            factor = (curvature + dot(change, hy)) / curvature**2
            updated = [
                [
                    h[i][j]
                    + factor * displacement[i] * displacement[j]
                    - (hy[i] * displacement[j] + displacement[i] * hy[j]) / curvature
                    for j in range(n)
                ]
                for i in range(n)
            ]
            magnitude = 1.0
            maximum = max(abs(v) for row in updated for v in row)
            while magnitude < maximum:
                magnitude *= 10
            h = [[quantize(v / magnitude, 10) * magnitude for v in row] for row in updated]
        x, value, gradient = candidate, trial, new_gradient
    return {
        "x": np.array(x),
        "converged": bool(max(map(abs, gradient)) < 1e-6),
        "iterations": iteration + 1,
    }
