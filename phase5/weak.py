"""Angle-only weak moments for the four-term pendulum library."""

from functools import lru_cache

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.polynomial.legendre import leggauss


@lru_cache(maxsize=32)
def weak_weights(window: int, power: int, dt_s: float) -> np.ndarray:
    """Integrate the test function and its time derivatives against sample hats."""
    if window < 3 or window % 2 == 0 or power < 3 or not np.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("Expected an odd window, power at least three and positive time step.")
    half_width = (window - 1) * dt_s / 2
    grid = np.linspace(-1.0, 1.0, window)
    nodes, quadrature = leggauss(power + 1)
    local = (nodes + 1) / 2
    s = grid[:-1, None] + np.diff(grid)[:, None] * local
    inside = 1 - s**2
    phi = inside**power
    dphi = -2 * power * s * inside**(power - 1) / half_width
    ddphi = (
        -2 * power * inside**(power - 1)
        + 4 * power * (power - 1) * s**2 * inside**(power - 2)
    ) / half_width**2
    weights = np.empty((3, window))
    for row, function in enumerate((phi, -dphi, ddphi)):
        weighted = function * (dt_s / 2 * quadrature)
        weights[row] = 0
        weights[row, :-1] += weighted @ (1 - local)
        weights[row, 1:] += weighted @ local
    weights /= weights[0].sum()
    weights.setflags(write=False)
    return weights


def weak_design(theta: np.ndarray, dt_s: float, window: int, power: int, trim: int):
    """Return normalized weak library rows and acceleration moments."""
    theta = np.asarray(theta, dtype=float)
    half = window // 2
    if theta.ndim != 1 or not np.isfinite(theta).all() or trim < half or theta.size <= 2 * trim:
        raise ValueError("The weak window must fit the common interior of a finite observation.")
    weights = weak_weights(window, power, dt_s)
    start = trim - half
    stop = start + theta.size - 2 * trim

    def windows(values):
        return sliding_window_view(values, window)[start:stop]

    angle = windows(theta)
    design = np.column_stack((
        angle @ weights[0],
        windows(theta**3) @ weights[0],
        windows(np.sin(theta)) @ weights[0],
        angle @ weights[1],
    ))
    return design, angle @ weights[2]
