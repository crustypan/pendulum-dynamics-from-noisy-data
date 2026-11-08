"""Trajectory-level prediction metrics with explicit physical parameter applicability."""

import numpy as np

from pendulum_research.physics import Trajectory


def trajectory_metrics(reference: Trajectory, prediction: Trajectory) -> dict:
    if not np.array_equal(reference.time, prediction.time):
        raise ValueError("Trajectory metrics require identical observation times.")
    if not np.isfinite(reference.theta).all() or not np.isfinite(prediction.theta).all():
        raise ValueError("Trajectory metrics require finite angles.")
    true_period = reference.period_s
    predicted_period = prediction.period_s
    return {
        "theta_rmse_rad": float(np.sqrt(np.mean((prediction.theta - reference.theta)**2))),
        "reference_period_s": true_period,
        "predicted_period_s": predicted_period,
        "period_relative_error": (
            abs(predicted_period - true_period) / true_period
            if true_period is not None and predicted_period is not None else None
        ),
    }


def angle_coverage(angle_deg: float, training_angles: list[float]) -> str:
    return "interpolation" if min(training_angles) <= angle_deg <= max(training_angles) else "extrapolation"
