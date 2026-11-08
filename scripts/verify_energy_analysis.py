"""Recompute saved drift metrics and audit the previous-phase linkage."""

import argparse
import csv
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np

from pendulum_research.energy import energy_drift
from pendulum_research.noise_study import model_from_record
from pendulum_research.physics import physical_energy
from pendulum_research.sindy import COEFFICIENT_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
NOISE = ROOT / "results/noise_sindy"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def verify(output: Path) -> dict:
    assert json.loads((output / "run_status.json").read_text()) == {"phase": 3, "status": "completed"}
    for line in (output / "SHA256SUMS").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        path = (ROOT / relative).resolve()
        assert path.is_relative_to(ROOT) and digest(path) == expected, relative
    metadata = json.loads((output / "run_metadata.json").read_text())
    for file in ("source_sha256", "input_sha256"):
        paths = metadata[file] if file in metadata else json.loads((output / "input_sha256.json").read_text())
        for relative, expected in paths.items():
            assert digest(ROOT / relative) == expected, relative
    config = json.loads((output / "config.json").read_text())
    assert config["physical_k_s2"] == 9.81 == metadata["physical_k_s2"]

    coefficient_rows = {row["model_id"]: row for row in read_rows(NOISE / "selected_models.csv")}
    model_rows = {row["model_id"]: row for row in read_rows(output / "model_energy.csv")}
    assert model_rows.keys() == {name for name, row in coefficient_rows.items() if row["fit_status"] == "selected"}
    for name, row in model_rows.items():
        exact = tuple(Fraction(Decimal(row[column])) for column in COEFFICIENT_COLUMNS)
        assert all(row[column] == coefficient_rows[name][column] for column in COEFFICIENT_COLUMNS)
        assert Fraction(row["physical_rate_sine_residual_exact"]) == exact[2] + Fraction(981, 100)
        assert int(row["physical_rate_zero_for_all_states"]) == (exact == (0, 0, -Fraction(981, 100), 0))

    trajectories = read_rows(output / "trajectory_energy.csv")
    phase2 = read_rows(NOISE / "test_metrics.csv")
    assert len(trajectories) == len(phase2) == metadata["intended_rollouts"]
    with np.load(NOISE / "test_predictions.npz", allow_pickle=False) as source:
        theta, omega, nominal_time = source["theta_rad"], source["omega_rad_s"], source["time_s"]
    with np.load(output / "energy_traces.npz", allow_pickle=False) as traces:
        np.testing.assert_array_equal(traces["nominal_time_s"], nominal_time)
        nominal_energy, rates = traces["nominal_physical_energy"], traces["nominal_physical_rate"]
        refined_energy, tight_time = traces["tightened_physical_energy"], traces["tight_time_s"]
    stride = round((nominal_time[1] - nominal_time[0]) / (tight_time[1] - tight_time[0]))
    np.testing.assert_allclose(tight_time[::stride], nominal_time, rtol=0, atol=1e-14)
    assert theta.shape == nominal_energy.shape == rates.shape
    assert refined_energy.shape == (len(trajectories), len(tight_time))

    nominal_count, tight_count = 0, 0
    for index, (row, original) in enumerate(zip(trajectories, phase2)):
        for field in ("prediction_index", "model_id", "seed", "training_set", "method", "coverage"):
            assert row[field] == original[field]
        assert float(row["angle_deg"]) == float(original["angle_deg"])
        assert int(row["prediction_index"]) == index and row["nominal_status"] == original["status"]
        if row["nominal_status"] == "completed":
            energy = physical_energy(theta[index], omega[index], 9.81)
            np.testing.assert_array_equal(energy, nominal_energy[index])
            nominal_count += 1
            np.testing.assert_allclose(energy_drift(energy), float(row["nominal_drift"]), atol=1e-15, rtol=1e-13)
            model = model_from_record(coefficient_rows[row["model_id"]])
            acceleration = np.array([model.acceleration(t, w) for t, w in zip(theta[index], omega[index])])
            power = omega[index] * (acceleration + 9.81 * np.sin(theta[index]))
            np.testing.assert_allclose(power, rates[index], atol=5e-7, rtol=1e-10)
            np.testing.assert_allclose(np.max(np.abs(rates[index])), float(row["max_abs_physical_rate_s3"]),
                                       atol=1e-15, rtol=1e-13)
        else:
            assert not row["nominal_drift"] and np.isnan(nominal_energy[index]).all() and np.isnan(rates[index]).all()

        if row["tight_status"] == "completed":
            tight_count += 1
            shared, fine = energy_drift(refined_energy[index, ::stride]), energy_drift(refined_energy[index])
            np.testing.assert_allclose([shared, fine], [float(row["tight_shared_drift"]), float(row["tight_fine_drift"])],
                                       atol=1e-15, rtol=1e-13)
            assert fine >= shared
            if row["nominal_drift"]:
                nominal = float(row["nominal_drift"])
                gap = abs(nominal - shared)
                bound = config["drift_agreement_absolute"] + config["drift_agreement_relative"] * max(nominal, shared)
                assert int(row["solver_drift_within_tolerance"]) == (gap <= bound)
                np.testing.assert_allclose(gap, float(row["solver_drift_absolute_gap"]), atol=1e-15, rtol=1e-13)
        else:
            assert not row["tight_fine_drift"] and np.isnan(refined_energy[index]).all()

    assert nominal_count == metadata["nominal_completed"] and tight_count == metadata["tight_completed"]
    return {"status": "verified", "exact_coefficient_records": len(model_rows),
            "rollouts": len(trajectories), "nominal_completed": nominal_count,
            "tight_completed": tight_count, "saved_rates_checked": nominal_count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results/energy_drift")
    output = parser.parse_args().results.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Use a results directory within the project.")
    print(json.dumps(verify(output), indent=2))


if __name__ == "__main__":
    main()
