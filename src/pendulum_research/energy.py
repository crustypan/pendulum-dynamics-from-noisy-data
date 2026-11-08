"""Numerical evaluations of the energy functions and rates proved in Lean."""

import numpy as np

from pendulum_research.sindy import SparseModel


def relative_change(energy: np.ndarray) -> np.ndarray:
    """Normalize changes by a positive initial energy on a finite sampled path."""
    values = np.asarray(energy, dtype=float)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all() or values[0] <= 0:
        raise ValueError("Energy change requires a finite series and positive initial energy.")
    return (values - values[0]) / values[0]


def energy_drift(energy: np.ndarray) -> float:
    return float(np.max(np.abs(relative_change(energy))))


def sindy_physical_rate(model: SparseModel, theta: np.ndarray, omega: np.ndarray, k: float) -> np.ndarray:
    linear, cubic, sine, velocity = model.coefficients
    return omega * (linear * theta + cubic * theta**3 + (sine + k) * np.sin(theta) + velocity * omega)


def sindy_model_energy(model: SparseModel, theta: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """Evaluate the fitted potential plus kinetic energy, with potential zero at theta = 0."""
    linear, cubic, sine, _ = model.coefficients
    return omega**2 / 2 - linear * theta**2 / 2 - cubic * theta**4 / 4 - 2 * sine * np.sin(theta / 2)**2


def sine_energy_difference(k: float, c_sine: float, theta: np.ndarray) -> np.ndarray:
    """Analytic change of reference energy on a sine-only solution."""
    potential = 2 * np.sin(theta / 2)**2
    return (k + c_sine) * (potential - potential[0])
