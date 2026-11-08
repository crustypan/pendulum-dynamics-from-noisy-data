"""Check the numerical counterparts of the Lean rate and conservation identities."""

import numpy as np
import pytest

from pendulum_research.energy import energy_drift, sine_energy_difference, sindy_model_energy, sindy_physical_rate
from pendulum_research.physics import Simulation, physical_energy
from pendulum_research.sindy import SparseModel, rollout


def test_physical_rate_matches_directional_derivative():
    model = SparseModel((1.4, -0.75, -8.2, 0.3))
    theta, omega, k, step = 0.7, -1.2, 9.81, 1e-6
    acceleration = model.acceleration(theta, omega)
    upper = physical_energy(theta + step * omega, omega + step * acceleration, k)
    lower = physical_energy(theta - step * omega, omega - step * acceleration, k)
    assert (upper - lower) / (2 * step) == pytest.approx(
        sindy_physical_rate(model, theta, omega, k), abs=1e-8
    )


def test_fitted_energy_rate_is_velocity_coefficient_times_speed_squared():
    model = SparseModel((1.4, -0.75, -8.2, -0.3))
    theta, omega, step = 0.7, -1.2, 1e-6
    acceleration = model.acceleration(theta, omega)
    upper = sindy_model_energy(model, theta + step * omega, omega + step * acceleration)
    lower = sindy_model_energy(model, theta - step * omega, omega - step * acceleration)
    assert (upper - lower) / (2 * step) == pytest.approx(model.coefficients[3] * omega**2, abs=1e-8)


def test_sine_only_energy_difference_in_a_guarded_rollout():
    k = 9.81
    model = SparseModel((0, 0, -8.2, 0))
    status, path = rollout(model, 75, Simulation(), {"angle_limit_rad": 6.3, "speed_limit_rad_s": 100})
    assert status == "completed"
    energy = physical_energy(path.theta, path.omega, k)
    np.testing.assert_allclose(
        energy - energy[0], sine_energy_difference(k, model.coefficients[2], path.theta),
        rtol=0, atol=1e-9,
    )
    assert energy_drift(sindy_model_energy(model, path.theta, path.omega)) < 1e-8


def test_reference_field_has_zero_pointwise_physical_rate():
    theta = np.linspace(-np.pi, np.pi, 11)
    omega = np.linspace(-2, 3, theta.size)
    np.testing.assert_array_equal(sindy_physical_rate(SparseModel((0, 0, -9.81, 0)), theta, omega, 9.81),
                                  np.zeros(theta.size))


@pytest.mark.parametrize("values", [[0.0, 1.0], [-1.0, 2.0], [1.0, np.nan]])
def test_undefined_relative_drift_is_rejected(values):
    with pytest.raises(ValueError, match="positive initial energy"):
        energy_drift(np.array(values))
