"""Numerical trajectories and independent physical reference checks."""

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.integrate import solve_ivp
from scipy.special import ellipk


@dataclass(frozen=True)
class Simulation:
    duration_s: float = 10.0
    dt_s: float = 0.02
    rtol: float = 1e-11
    atol: float = 1e-13
    max_step_s: float = 0.1

    def time_grid(self) -> np.ndarray:
        values = (self.duration_s, self.dt_s, self.rtol, self.atol, self.max_step_s)
        if not np.isfinite(values).all() or min(values) <= 0:
            raise ValueError("Simulation settings must be positive.")
        steps = round(self.duration_s / self.dt_s)
        if steps < 4 or not np.isclose(steps * self.dt_s, self.duration_s, rtol=0, atol=1e-12):
            raise ValueError("Duration must contain an integer number of sampling intervals.")
        return np.linspace(0, self.duration_s, steps + 1)


@dataclass(frozen=True)
class Trajectory:
    time: np.ndarray
    theta: np.ndarray
    omega: np.ndarray
    descending_crossings: np.ndarray

    @property
    def period_s(self) -> float | None:
        intervals = np.diff(self.descending_crossings)
        return float(np.median(intervals)) if intervals.size else None


def simulate(
    acceleration: Callable[[float], float],
    angle_deg: float,
    settings: Simulation,
    omega0: float = 0.0,
) -> Trajectory:
    """Integrate from a specified initial condition and detect same-direction crossings."""
    time = settings.time_grid()
    if not np.isfinite([angle_deg, omega0]).all():
        raise ValueError("Initial conditions must be finite.")

    def rhs(_time, state):
        return (state[1], acceleration(state[0]))

    def descending_crossing(_time, state):
        return state[0]

    descending_crossing.direction = -1
    solution = solve_ivp(
        rhs, (time[0], time[-1]), (np.deg2rad(angle_deg), omega0),
        t_eval=time, events=descending_crossing, method="DOP853",
        rtol=settings.rtol, atol=settings.atol, max_step=settings.max_step_s,
    )
    if not solution.success or solution.t.size != time.size or not np.isfinite(solution.y).all():
        raise RuntimeError(f"Trajectory integration failed. {solution.message}")
    return Trajectory(time, solution.y[0], solution.y[1], solution.t_events[0])


def reference_trajectory(angle_deg: float, k: float, settings: Simulation) -> Trajectory:
    if not np.isfinite(k) or k <= 0:
        raise ValueError("The physical reference requires a positive finite k.")
    return simulate(lambda theta: -k * np.sin(theta), angle_deg, settings)


def physical_energy(theta, omega, k: float) -> np.ndarray:
    """Use a stable form of k * (1 - cos(theta))."""
    return 0.5 * np.asarray(omega)**2 + 2 * k * np.sin(np.asarray(theta) / 2)**2


def relative_energy_drift(trajectory: Trajectory, k: float) -> float:
    energy = physical_energy(trajectory.theta, trajectory.omega, k)
    if energy[0] <= 0:
        raise ValueError("Relative energy drift requires a positive initial energy.")
    return float(np.max(np.abs(energy - energy[0])) / energy[0])


def exact_reference_period(angle_deg: float, k: float) -> float:
    """SciPy ellipk takes the parameter m, which is the squared elliptic modulus."""
    if not 0 < abs(angle_deg) < 180 or not np.isfinite(k) or k <= 0:
        raise ValueError("The period formula requires a nonzero libration amplitude and k > 0.")
    parameter = np.sin(np.deg2rad(angle_deg) / 2)**2
    return float(4 * ellipk(parameter) / np.sqrt(k))
