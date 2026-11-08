"""Four-term pendulum library, STLSQ and guarded trajectory integration."""

from dataclasses import dataclass
import math

import numpy as np
from scipy.integrate import solve_ivp

from pendulum_research.physics import Simulation, Trajectory

TERMS = ("theta", "theta_cubed", "sin_theta", "omega")
COEFFICIENT_COLUMNS = tuple(f"c_{name}" for name in TERMS)


def feature_matrix(theta: np.ndarray, omega: np.ndarray) -> np.ndarray:
    return np.column_stack((theta, theta**3, np.sin(theta), omega))


@dataclass(frozen=True)
class SparseModel:
    coefficients: tuple[float, float, float, float]

    @property
    def support(self) -> tuple[str, ...]:
        return tuple(name for name, value in zip(TERMS, self.coefficients) if value != 0)

    @property
    def equation(self) -> str:
        basis = ("theta", "theta^3", "sin(theta)", "omega")
        terms = [f"({value:.10g}) * {term}" for term, value in zip(basis, self.coefficients) if value != 0]
        return "omega_dot = " + (" + ".join(terms) or "0")

    def acceleration(self, theta: float, omega: float) -> float:
        linear, cubic, sine, velocity = self.coefficients
        return linear * theta + cubic * theta**3 + sine * math.sin(theta) + velocity * omega


def fit_stlsq(design: np.ndarray, target: np.ndarray, threshold: float, alpha: float) -> SparseModel:
    """Threshold dimensionless ridge coefficients, then refit the surviving support."""
    design = np.asarray(design, dtype=float)
    target = np.asarray(target, dtype=float)
    if (design.ndim != 2 or design.shape[1] != len(TERMS) or design.shape[0] == 0
            or target.shape != (design.shape[0],) or not np.isfinite(design).all()
            or not np.isfinite(target).all() or not np.isfinite([threshold, alpha]).all()
            or min(threshold, alpha) < 0):
        raise ValueError("STLSQ requires finite, aligned training arrays and nonnegative settings.")
    feature_scale = np.sqrt(np.mean(design**2, axis=0))
    target_scale = float(np.sqrt(np.mean(target**2)))
    active = np.flatnonzero(feature_scale > 0)
    coefficients = np.zeros(len(TERMS))
    if target_scale == 0:
        return SparseModel(tuple(coefficients.tolist()))
    response = target / target_scale

    while active.size:
        columns = design[:, active] / feature_scale[active]
        # Minimize mean squared scaled residual plus alpha times squared weights.
        regularized = np.vstack((columns, np.sqrt(alpha * design.shape[0]) * np.eye(active.size)))
        ridge_weights = np.linalg.lstsq(regularized, np.r_[response, np.zeros(active.size)], rcond=None)[0]
        retained = np.abs(ridge_weights) >= threshold
        if retained.all():
            weights = np.linalg.lstsq(columns, response, rcond=None)[0]
            coefficients[active] = weights * target_scale / feature_scale[active]
            break
        active = active[retained]
    return SparseModel(tuple(coefficients.tolist()))


def rollout(
    model: SparseModel, angle_deg: float, settings: Simulation, limits: dict,
) -> tuple[str, Trajectory | None]:
    """Return a full sampled trajectory or an explicit failure status."""
    times = settings.time_grid()

    def rhs(_time, state):
        theta, omega = state
        return omega, model.acceleration(theta, omega)

    def crossing(_time, state):
        return state[0]

    crossing.direction = -1

    def state_guard(_time, state):
        return min(limits["angle_limit_rad"] - abs(state[0]),
                   limits["speed_limit_rad_s"] - abs(state[1]))

    state_guard.direction = -1
    state_guard.terminal = True
    if abs(math.radians(angle_deg)) >= limits["angle_limit_rad"]:
        return "state_limit", None
    try:
        with np.errstate(over="raise", invalid="raise"):
            solution = solve_ivp(
                rhs, (times[0], times[-1]), (math.radians(angle_deg), 0.0),
                method="DOP853", t_eval=times, events=(crossing, state_guard),
                rtol=settings.rtol, atol=settings.atol, max_step=settings.max_step_s,
            )
    except (FloatingPointError, OverflowError):
        return "numerical_failure", None
    if solution.status == 1:
        return "state_limit", None
    if not solution.success or solution.t.size != times.size or not np.isfinite(solution.y).all():
        return "numerical_failure", None
    return "completed", Trajectory(times, solution.y[0], solution.y[1], solution.t_events[0])
