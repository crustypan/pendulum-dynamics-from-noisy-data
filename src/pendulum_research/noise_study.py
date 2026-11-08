"""Training-only sparse fits and validation-only hyperparameter selection."""

import json
from statistics import mean

import numpy as np

from pendulum_research.evaluation import angle_coverage, trajectory_metrics
from pendulum_research.noise import Preprocessing, estimate_derivatives
from pendulum_research.physics import Simulation, Trajectory
from pendulum_research.sindy import COEFFICIENT_COLUMNS, SparseModel, feature_matrix, fit_stlsq, rollout


def rmse(actual: np.ndarray, expected: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - expected)**2)))


def fit_diagnostics(design: np.ndarray) -> dict:
    correlation = np.corrcoef(design, rowvar=False)
    scales = np.sqrt(np.mean(design**2, axis=0))
    condition = np.linalg.cond(design / np.where(scales > 0, scales, 1))
    return {
        "corr_theta_cubic": float(correlation[0, 1]) if np.isfinite(correlation[0, 1]) else None,
        "corr_theta_sine": float(correlation[0, 2]) if np.isfinite(correlation[0, 2]) else None,
        "corr_cubic_sine": float(correlation[1, 2]) if np.isfinite(correlation[1, 2]) else None,
        "scaled_condition_number": float(condition) if np.isfinite(condition) else None,
    }


def validation_score(model: SparseModel, observations: dict, settings: Simulation, limits: dict) -> dict:
    errors = {}
    failures = {}
    for angle, theta_obs in observations.items():
        status, prediction = rollout(model, angle, settings, limits)
        if prediction is None:
            failures[str(angle)] = status
        else:
            errors[str(angle)] = rmse(prediction.theta, theta_obs)
    return {
        "validation_status": "incomplete" if failures else "completed",
        "validation_rmse_rad": None if failures else mean(errors.values()),
        "validation_per_angle_rmse": json.dumps(errors, sort_keys=True),
        "validation_failures": json.dumps(failures, sort_keys=True),
    }


def select_case(
    training: dict, validation: dict, settings: Simulation,
    variants: tuple[Preprocessing, ...], config: dict,
) -> tuple[dict, list[dict]]:
    """Select a candidate using observed validation angles and no test data."""
    if not training or not validation or set(training).intersection(validation):
        raise ValueError("Training and validation must contain disjoint trajectories.")
    expected_samples = settings.time_grid().size
    if any(values.shape != (expected_samples,) for values in (*training.values(), *validation.values())):
        raise ValueError("All observations must have the configured number of samples.")
    grid = []
    scores = {}
    for method in variants:
        estimates = [
            estimate_derivatives(theta, settings.dt_s, method, config["preprocessing"]["trim_per_end"])
            for theta in training.values()
        ]
        design = np.vstack([feature_matrix(item.theta, item.omega) for item in estimates])
        target = np.concatenate([item.acceleration for item in estimates])
        diagnostics = fit_diagnostics(design)
        for threshold in config["stlsq"]["thresholds"]:
            model = fit_stlsq(design, target, threshold, config["stlsq"]["ridge_alpha"])
            if model.coefficients not in scores:
                scores[model.coefficients] = validation_score(model, validation, settings, config["rollout"])
            grid.append({
                "candidate_index": len(grid),
                "window_samples": method.window, "polynomial_order": method.order,
                "threshold": threshold,
                "support": "+".join(model.support) or "empty", "term_count": len(model.support),
                **dict(zip(COEFFICIENT_COLUMNS, model.coefficients)),
                "equation": model.equation,
                "train_acceleration_rmse_rad_s2": rmse(design @ model.coefficients, target),
                **diagnostics,
                **scores[model.coefficients],
                "selected": 0,
            })

    eligible = [row for row in grid if row["validation_status"] == "completed"]
    if eligible:
        best = min(row["validation_rmse_rad"] for row in eligible)
        tie_limit = best + config["validation"]["tie_tolerance_rad"]
        winner = min(
            (row for row in eligible if row["validation_rmse_rad"] <= tie_limit),
            key=lambda row: (row["term_count"], row["validation_rmse_rad"], row["candidate_index"]),
        )
        winner["selected"] = 1
        selected = dict(winner)
    else:
        selected = dict.fromkeys(grid[0])
    selected.update({
        "fit_status": "selected" if eligible else "no_valid_validation",
        "candidate_count": len(grid),
        "valid_candidate_count": len(eligible),
    })
    return selected, grid


def model_from_record(record: dict) -> SparseModel | None:
    if record["fit_status"] != "selected":
        return None
    model = SparseModel(tuple(float(record[column]) for column in COEFFICIENT_COLUMNS))
    if ("+".join(model.support) or "empty") != record["support"] or model.equation != record["equation"]:
        raise ValueError("The saved SINDy model disagrees with its coefficients.")
    return model


def evaluate_test_angles(
    model: SparseModel | None, references: dict[float, Trajectory], training_angles: list[float],
    settings: Simulation, limits: dict,
) -> list[tuple[dict, Trajectory | None]]:
    evaluations = []
    for angle, reference in references.items():
        status, prediction = rollout(model, angle, settings, limits) if model else ("no_selected_model", None)
        row = {
            "angle_deg": angle, "coverage": angle_coverage(angle, training_angles), "status": status,
            "theta_rmse_rad": None, "reference_period_s": reference.period_s,
            "predicted_period_s": None, "period_relative_error": None,
        }
        if prediction is not None:
            row.update(trajectory_metrics(reference, prediction))
        evaluations.append((row, prediction))
    return evaluations


def derivative_errors(
    method: Preprocessing, theta_obs: np.ndarray, reference: Trajectory,
    k: float, dt_s: float, trim: int,
) -> dict:
    estimates = estimate_derivatives(theta_obs, dt_s, method, trim)
    theta = reference.theta[trim:-trim]
    return {
        "angle_rmse_rad": rmse(estimates.theta, theta),
        "velocity_rmse_rad_s": rmse(estimates.omega, reference.omega[trim:-trim]),
        "acceleration_rmse_rad_s2": rmse(estimates.acceleration, -k * np.sin(theta)),
    }
