"""Numerical correctness checks for Phase 1."""

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from pendulum_research.data_generation import load_config
from pendulum_research.evaluation import angle_coverage, trajectory_metrics
from pendulum_research.models import Model, angle_derivatives, fit_models
from pendulum_research.physics import (
    Simulation, exact_reference_period, reference_trajectory, relative_energy_drift, simulate,
)

ROOT = Path(__file__).resolve().parents[1]


def test_sampling_grid():
    time = Simulation().time_grid()
    assert time.size == 501 and time[0] == 0 and time[-1] == 10
    np.testing.assert_allclose(np.diff(time), 0.02, rtol=0, atol=1e-14)


def test_nonintegral_sampling_is_rejected():
    with pytest.raises(ValueError):
        Simulation(duration_s=1, dt_s=0.03).time_grid()


def test_declared_splits_are_disjoint():
    splits = load_config(ROOT / "configs/baseline.json")["splits"]
    assert set(splits["training_A"]) < set(splits["training_B"])
    assert set(splits["validation"]).isdisjoint(splits["test"])


def test_leaking_split_is_rejected(tmp_path):
    config = json.loads((ROOT / "configs/baseline.json").read_text())
    config["splits"]["training_A"].append(config["splits"]["test"][0])
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="overlaps"):
        load_config(path)


@pytest.mark.parametrize("angle", [5, 30, 90])
def test_reference_energy_and_period(angle):
    trajectory = reference_trajectory(angle, 9.81, Simulation())
    assert relative_energy_drift(trajectory, 9.81) < 1e-8
    assert abs(trajectory.period_s - exact_reference_period(angle, 9.81)) < 1e-8


def test_linear_analytic_solution():
    a, angle = 8.0, 30.0
    trajectory = simulate(lambda theta: -a * theta, angle, Simulation())
    expected = np.deg2rad(angle) * np.cos(np.sqrt(a) * trajectory.time)
    np.testing.assert_allclose(trajectory.theta, expected, rtol=0, atol=1e-8)
    assert abs(trajectory.period_s - 2 * np.pi / np.sqrt(a)) < 1e-8


def test_tighter_tolerances_agree():
    settings = Simulation()
    normal = reference_trajectory(90, 9.81, settings)
    tight = reference_trajectory(90, 9.81, replace(settings, rtol=1e-13, atol=1e-15))
    np.testing.assert_allclose(normal.theta, tight.theta, rtol=0, atol=1e-8)


def test_five_point_derivative():
    time = Simulation().time_grid()
    theta = np.cos(1.7 * time)
    interior, acceleration = angle_derivatives(theta, 0.02)
    np.testing.assert_allclose(acceleration, -(1.7**2) * interior, rtol=0, atol=1e-6)
    assert interior.size == 497


@pytest.mark.parametrize("model", [Model("M1", 3.2), Model("M2", 6.4), Model("M3", 6.4, -0.3)])
def test_known_synthetic_coefficients_are_recovered(model):
    observed = simulate(model.acceleration, 30, Simulation()).theta
    learned = fit_models([observed], 0.02)[model.name]
    assert abs(learned.a - model.a) < 1e-5
    assert abs(learned.b - model.b) < 1e-5


@pytest.mark.parametrize("model", [Model("M1", 8.1), Model("M2", 7.4), Model("M3", 9.1, -1.2)])
@pytest.mark.parametrize("include_equation", [False, True])
def test_model_serialization(model, include_equation):
    saved = model.to_dict()
    if include_equation:
        saved["equation"] = model.equation
    restored = Model.from_dict(json.loads(json.dumps(saved)))
    theta = np.array([-1.0, 0.0, 0.5, 1.5])
    np.testing.assert_array_equal(restored.acceleration(theta), model.acceleration(theta))


def test_identical_trajectory_has_zero_error():
    trajectory = reference_trajectory(30, 9.81, Simulation())
    metrics = trajectory_metrics(trajectory, trajectory)
    assert metrics["theta_rmse_rad"] == 0 and metrics["period_relative_error"] == 0


def test_different_time_grids_are_rejected():
    first = reference_trajectory(30, 9.81, Simulation())
    second = reference_trajectory(30, 9.81, Simulation(dt_s=0.01))
    with pytest.raises(ValueError, match="identical"):
        trajectory_metrics(first, second)


def test_relative_energy_requires_positive_initial_energy():
    equilibrium = reference_trajectory(0, 9.81, Simulation())
    with pytest.raises(ValueError, match="positive"):
        relative_energy_drift(equilibrium, 9.81)


def test_coverage_depends_on_training_range():
    assert angle_coverage(45, [5, 15, 30]) == "extrapolation"
    assert angle_coverage(45, [5, 15, 30, 60]) == "interpolation"
    assert angle_coverage(90, [5, 15, 30, 60]) == "extrapolation"


def test_inconsistent_saved_equation_is_rejected():
    model = Model("M2", 7.4)
    with pytest.raises(ValueError, match="disagrees"):
        Model.from_dict({**model.to_dict(), "equation": "theta_ddot = 0"})
