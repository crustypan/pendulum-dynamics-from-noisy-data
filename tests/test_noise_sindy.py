"""Deterministic checks for angle-only preprocessing, sparse fitting and rollout."""

import json
from pathlib import Path

import numpy as np
import pytest

from pendulum_research.noise import Preprocessing, estimate_derivatives, observe_theta
from pendulum_research.noise_study import evaluate_test_angles, model_from_record, select_case
from pendulum_research.physics import Simulation, reference_trajectory
from pendulum_research.sindy import COEFFICIENT_COLUMNS, SparseModel, feature_matrix, fit_stlsq, rollout

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs/noise.json").read_text())


def test_noise_scale_radians_and_reproducible_independent_streams():
    clean = np.zeros(30_000)
    args = (clean, 2, 20261107, 2, 3)
    first = observe_theta(*args, 0)
    np.testing.assert_array_equal(first, observe_theta(*args, 0))
    assert abs(np.std(first) / np.deg2rad(2) - 1) < 0.02
    assert abs(np.mean(first)) < 0.02 * np.deg2rad(2)
    assert abs(np.corrcoef(first, observe_theta(*args, 1))[0, 1]) < 0.03
    np.testing.assert_array_equal(observe_theta(clean, 0, 20261107, 0, 0, 0), clean)


@pytest.mark.parametrize("method", [Preprocessing("direct"), Preprocessing("savgol", 41, 4)])
def test_derivatives_align_and_use_physical_sampling_interval(method):
    dt = 0.02
    time = np.arange(501) * dt
    signal = 1 + 0.2 * time + 0.7 * time**2
    estimates = estimate_derivatives(signal, dt, method, 20)
    assert estimates.theta.size == 461
    np.testing.assert_allclose(estimates.theta, signal[20:-20], rtol=0, atol=1e-8)
    np.testing.assert_allclose(estimates.omega, 0.2 + 1.4 * time[20:-20], rtol=0, atol=1e-8)
    np.testing.assert_allclose(estimates.acceleration, 1.4, rtol=0, atol=1e-8)


def test_stlsq_recovers_an_independent_known_sparse_system():
    rng = np.random.default_rng(19)
    theta = rng.uniform(-2.5, 2.5, 501)
    omega = rng.normal(size=theta.shape)
    design = feature_matrix(theta, omega)
    target = -7.3 * np.sin(theta) - 0.85 * omega
    model = fit_stlsq(design, target, 0.02, 1e-8)
    assert model.support == ("sin_theta", "omega")
    np.testing.assert_allclose(model.coefficients, [0, 0, -7.3, -0.85], rtol=0, atol=1e-11)
    # Compare the unregularized refit with an independent retained-column solve.
    expected = np.linalg.lstsq(design[:, [2, 3]], target, rcond=None)[0]
    np.testing.assert_allclose(np.asarray(model.coefficients)[[2, 3]], expected, rtol=0, atol=1e-11)
    np.testing.assert_allclose(model.acceleration(theta[2], omega[2]), target[2], rtol=0, atol=1e-11)
    assert fit_stlsq(design, target, 10, 1e-8).support == ()


def test_rollout_reproduces_the_reference_and_records_state_limit():
    settings = Simulation()
    reference = reference_trajectory(45, 9.81, settings)
    status, prediction = rollout(SparseModel((0, 0, -9.81, 0)), 45, settings, CONFIG["rollout"])
    assert status == "completed"
    np.testing.assert_allclose(prediction.theta, reference.theta, atol=1e-9, rtol=0)
    assert abs(prediction.period_s - reference.period_s) < 1e-9
    status, prediction = rollout(SparseModel((10, 10, 0, 0)), 90, settings, CONFIG["rollout"])
    assert (status, prediction) == ("state_limit", None)


def test_validation_uses_disjoint_data_and_can_reload_selected_model():
    settings = Simulation(duration_s=2)
    training = {angle: reference_trajectory(angle, 9.81, settings).theta for angle in (15, 30)}
    validation = {20: reference_trajectory(20, 9.81, settings).theta}
    direct = (Preprocessing("direct"),)
    with pytest.raises(ValueError, match="disjoint"):
        select_case(training, training, settings, direct, CONFIG)
    selected, grid = select_case(training, validation, settings, direct, CONFIG)
    assert selected["fit_status"] == "selected"
    assert sum(row["selected"] for row in grid) == 1
    assert selected["validation_rmse_rad"] <= min(
        row["validation_rmse_rad"] for row in grid if row["validation_status"] == "completed"
    ) + CONFIG["validation"]["tie_tolerance_rad"]
    model = model_from_record(selected)
    assert model.coefficients == tuple(selected[key] for key in COEFFICIENT_COLUMNS)


def test_failed_test_has_no_invented_metric():
    settings = Simulation(duration_s=2)
    references = {90: reference_trajectory(90, 9.81, settings)}
    (row, prediction), = evaluate_test_angles(
        SparseModel((10, 10, 0, 0)), references, [5, 15, 30], settings, CONFIG["rollout"]
    )
    assert row["status"] == "state_limit" and row["theta_rmse_rad"] is None
    assert row["coverage"] == "extrapolation" and prediction is None
