"""Paired angle-only observations and time-aligned derivative estimates."""

from dataclasses import dataclass
from itertools import product

import numpy as np
from scipy.signal import savgol_filter


@dataclass(frozen=True)
class Preprocessing:
    method: str
    window: int | None = None
    order: int | None = None


@dataclass(frozen=True)
class Estimates:
    theta: np.ndarray
    omega: np.ndarray
    acceleration: np.ndarray


def preprocessors(config: dict) -> tuple[Preprocessing, ...]:
    return (
        Preprocessing("direct"),
        *(Preprocessing("savgol", window, order)
          for window, order in product(config["savgol_windows"], config["savgol_orders"])),
    )


def observe_theta(
    theta: np.ndarray, sigma_deg: float, master: int, noise_index: int, seed: int, angle_index: int,
) -> np.ndarray:
    """Return one Gaussian measurement realization in radians."""
    theta = np.asarray(theta, dtype=float)
    if not np.isfinite(sigma_deg) or sigma_deg < 0:
        raise ValueError("The noise standard deviation must be finite and nonnegative.")
    if sigma_deg == 0:
        return theta.copy()
    entropy = np.random.SeedSequence([master, noise_index, seed, angle_index])
    generator = np.random.Generator(np.random.PCG64(entropy))
    return theta + generator.normal(0.0, np.deg2rad(sigma_deg), size=theta.shape)


def estimate_derivatives(
    theta_obs: np.ndarray, dt_s: float, method: Preprocessing, trim: int,
) -> Estimates:
    """Keep only times at which all compared stencils use measured samples."""
    theta = np.asarray(theta_obs, dtype=float)
    if (theta.ndim != 1 or not np.isfinite(theta).all() or not np.isfinite(dt_s)
            or dt_s <= 0 or trim < 1 or theta.size <= 2 * trim):
        raise ValueError("The observation, time interval and common trim must be valid.")
    if method.method == "direct":
        return Estimates(
            theta[trim:-trim],
            (theta[trim + 1:theta.size - trim + 1] - theta[trim - 1:theta.size - trim - 1]) / (2 * dt_s),
            (theta[trim + 1:theta.size - trim + 1] - 2 * theta[trim:-trim]
             + theta[trim - 1:theta.size - trim - 1]) / dt_s**2,
        )
    if method.method != "savgol" or method.window is None or method.order is None:
        raise ValueError("A supported preprocessing method is required.")
    if method.window % 2 == 0 or not 2 <= method.order < method.window or method.window // 2 > trim:
        raise ValueError("Savitzky–Golay settings must fit within the common interior.")
    filtered = [
        savgol_filter(theta, method.window, method.order, deriv=degree, delta=dt_s)[trim:-trim]
        for degree in (0, 1, 2)
    ]
    return Estimates(*filtered)
