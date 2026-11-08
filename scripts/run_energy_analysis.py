#!/usr/bin/env python3
"""Analyze the physical energy of every frozen Phase 2 test rollout."""

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
import hashlib
from importlib import metadata
import json
from pathlib import Path

import numpy as np

from pendulum_research.energy import energy_drift, sine_energy_difference, sindy_model_energy, sindy_physical_rate
from pendulum_research.energy_reporting import plot_baseline_energy, plot_sindy_energy, summarize_energy
from pendulum_research.noise_reporting import grouped, write_rows
from pendulum_research.noise_study import model_from_record
from pendulum_research.physics import Simulation, physical_energy
from pendulum_research.sindy import COEFFICIENT_COLUMNS, rollout

ROOT = Path(__file__).resolve().parents[1]
NOISE = ROOT / "results/noise_sindy"
BASELINE = ROOT / "results/baseline"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        sha = hashlib.sha256()
        for chunk in iter(lambda: stream.read(2**20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def check_inputs() -> dict[str, str]:
    required = {
        NOISE: ("config.json", "reference_config.json", "reference.npz", "selected_models.csv",
                "selection_frozen.json", "test_metrics.csv", "test_predictions.npz"),
        BASELINE: ("models.json", "predictions.csv"),
    }
    hashes = {}
    for directory, names in required.items():
        if json.loads((directory / "run_status.json").read_text())["status"] != "completed":
            raise ValueError("The previous experiments must have completed.")
        manifest = dict(
            (relative, expected) for expected, relative in
            (line.split("  ", 1) for line in (directory / "SHA256SUMS").read_text().splitlines())
        )
        for name in names:
            path = directory / name
            relative = str(path.relative_to(ROOT))
            if digest(path) != manifest[relative]:
                raise ValueError(f"Previous-phase artifact differs from its digest: {relative}")
            hashes[relative] = manifest[relative]
    freeze = json.loads((NOISE / "selection_frozen.json").read_text())
    if freeze["selected_models_sha256"] != hashes["results/noise_sindy/selected_models.csv"]:
        raise ValueError("The selected model file must match the Phase 2 freeze record.")
    return hashes


def model_energy_records(records: list[dict], k: float) -> dict[str, dict]:
    models = {}
    expected_sine = -Fraction(Decimal(str(k)))
    for record in records:
        model = model_from_record(record)
        if model is None:
            continue
        exact = tuple(Fraction(Decimal(record[column])) for column in COEFFICIENT_COLUMNS)
        models[record["model_id"]] = {
            "model_id": record["model_id"], "trial_id": int(record["trial_id"]),
            "noise_std_deg": float(record["noise_std_deg"]), "seed": int(record["seed"]),
            "training_set": record["training_set"], "method": record["method"], "support": record["support"],
            **{column: record[column] for column in COEFFICIENT_COLUMNS},
            "phase2_equation": record["equation"],
            "physical_rate_sine_residual_exact": str(exact[2] - expected_sine),
            "sine_only": int(model.support == ("sin_theta",)),
            "physical_rate_zero_for_all_states": int(exact == (0, 0, expected_sine, 0)),
            "fitted_energy_rate_sign": "zero" if exact[3] == 0 else ("nonpositive" if exact[3] < 0 else "nonnegative"),
            "model": model,
        }
    return models


def evaluate_trajectories(models: dict, k: float, settings: Simulation, tight: Simulation,
                          limits: dict, config: dict, output: Path) -> list[dict]:
    rows = read_rows(NOISE / "test_metrics.csv")
    with np.load(NOISE / "test_predictions.npz", allow_pickle=False) as stored:
        time = stored["time_s"]
        theta, omega = stored["theta_rad"], stored["omega_rad_s"]
    tight_time = tight.time_grid()
    stride = round(settings.dt_s / tight.dt_s)
    if not np.allclose(tight_time[::stride], time, rtol=0, atol=1e-14):
        raise ValueError("The tightened output grid must include the original sample times.")
    if theta.shape != omega.shape or theta.shape != (len(rows), len(time)):
        raise ValueError("Test metrics and prediction arrays must align.")

    records = []
    energies = np.full_like(theta, np.nan)
    rates = np.full_like(theta, np.nan)
    fine_energies = np.full((len(rows), len(tight_time)), np.nan)
    for index, row in enumerate(rows):
        if int(row["prediction_index"]) != index:
            raise ValueError("Prediction indices must match the archived row order.")
        info = models.get(row["model_id"])
        model = info["model"] if info else None
        angle = float(row["angle_deg"])
        initial_energy = float(physical_energy(np.deg2rad(angle), 0.0, k))
        nominal = row["status"]
        tight_status, refined = rollout(model, angle, tight, limits) if model else ("no_selected_model", None)
        record = {
            "prediction_index": index, "model_id": row["model_id"], "seed": int(row["seed"]),
            "noise_std_deg": float(row["noise_std_deg"]), "training_set": row["training_set"],
            "method": row["method"], "angle_deg": angle, "coverage": row["coverage"],
            "support": info["support"] if info else "no_selected_model",
            "sine_only": info["sine_only"] if info else 0,
            "nominal_status": nominal, "tight_status": tight_status,
            "initial_physical_energy_s2": initial_energy,
            "theta_rmse_rad": float(row["theta_rmse_rad"]) if row["theta_rmse_rad"] else None,
            "nominal_drift": None, "max_abs_physical_rate_s3": None,
            "fitted_energy_change_scaled_by_physical_e0": None, "sine_energy_identity_residual": None,
            "tight_shared_drift": None, "tight_fine_drift": None,
            "tight_fine_minus_shared": None, "solver_drift_absolute_gap": None,
            "solver_drift_within_tolerance": None,
        }
        if nominal == "completed":
            if model is None:
                raise ValueError("A completed rollout needs archived coefficients.")
            energy = physical_energy(theta[index], omega[index], k)
            if not np.isclose(energy[0], initial_energy, rtol=1e-13, atol=1e-14):
                raise ValueError("Initial energy differs from the declared release state.")
            rate = sindy_physical_rate(model, theta[index], omega[index], k)
            own = sindy_model_energy(model, theta[index], omega[index])
            energies[index], rates[index] = energy, rate
            record["nominal_drift"] = energy_drift(energy)
            record["max_abs_physical_rate_s3"] = float(np.max(np.abs(rate)))
            record["fitted_energy_change_scaled_by_physical_e0"] = float(np.max(np.abs(own - own[0])) / energy[0])
            if record["sine_only"]:
                analytic = sine_energy_difference(k, model.coefficients[2], theta[index])
                record["sine_energy_identity_residual"] = float(np.max(np.abs(energy - energy[0] - analytic)) / energy[0])
        elif not np.isnan(theta[index]).all() or not np.isnan(omega[index]).all():
            raise ValueError("Incomplete nominal paths must have explicit missing samples.")

        if refined is not None:
            fine = physical_energy(refined.theta, refined.omega, k)
            fine_energies[index] = fine
            shared = energy_drift(fine[::stride])
            dense = energy_drift(fine)
            record.update(tight_shared_drift=shared, tight_fine_drift=dense, tight_fine_minus_shared=dense - shared)
            if record["nominal_drift"] is not None:
                nominal_drift = record["nominal_drift"]
                gap = abs(nominal_drift - shared)
                bound = config["drift_agreement_absolute"] + config["drift_agreement_relative"] * max(nominal_drift, shared)
                record.update(solver_drift_absolute_gap=gap, solver_drift_within_tolerance=int(gap <= bound))
        records.append(record)
        if (index + 1) % 60 == 0 or index + 1 == len(rows):
            print(json.dumps({"stage": "tightened_rollouts", "evaluated": index + 1, "total": len(rows)}), flush=True)
    np.savez_compressed(output / "energy_traces.npz", nominal_time_s=time, tight_time_s=tight_time,
                        nominal_physical_energy=energies, nominal_physical_rate=rates,
                        tightened_physical_energy=fine_energies)
    return records


def baseline_energy(k: float, figure: dict) -> tuple[list, list, np.ndarray, dict]:
    with np.load(NOISE / "reference.npz", allow_pickle=False) as reference:
        time = reference["time_s"]
        ref_by_angle = {float(a): physical_energy(t, w, k) for a, t, w in
                        zip(reference["angle_deg"], reference["theta_rad"], reference["omega_rad_s"])}
    reference_rows = [{"angle_deg": angle, "physical_drift": energy_drift(energy)}
                      for angle, energy in ref_by_angle.items()]
    selected_angle = float(figure["angle_deg"])
    traces = {"Reference": (ref_by_angle[selected_angle], ref_by_angle[selected_angle])}
    predicted = [row for row in read_rows(BASELINE / "predictions.csv") if row["split"] == "test"]
    coeffs = json.loads((BASELINE / "models.json").read_text())
    summary = []
    for (training, model, angle), rows in grouped(predicted, ("training_set", "model", "angle_deg")).items():
        theta = np.array([float(row["theta_rad"]) for row in rows])
        omega = np.array([float(row["omega_rad_s"]) for row in rows])
        observed_time = np.array([float(row["time_s"]) for row in rows])
        np.testing.assert_array_equal(observed_time, time)
        physical = physical_energy(theta, omega, k)
        fit = coeffs[training][model]
        a, b = fit["a"], fit.get("b", 0)
        if model == "M2":
            own = physical_energy(theta, omega, a)
        else:
            own = omega**2 / 2 + a * theta**2 / 2 + (b * theta**4 / 4 if model == "M3" else 0)
        summary.append({"training_set": training, "model": model, "angle_deg": float(angle),
                        "physical_drift": energy_drift(physical), "own_energy_drift": energy_drift(own)})
        if training == figure["training_set"] and float(angle) == selected_angle:
            traces[model] = physical, own
    return reference_rows, summary, time, traces


def run(config: dict, output: Path, figure_dir: Path):
    source = check_inputs()
    noise_config = json.loads((NOISE / "config.json").read_text())
    reference_config = json.loads((NOISE / "reference_config.json").read_text())
    k = config["physical_k_s2"]
    physics = reference_config["physics"]
    if k != 9.81 or k != physics["gravity_m_s2"] / physics["length_m"]:
        raise ValueError("Physical energy must use the frozen reference value k = 9.81.")
    nominal_settings = Simulation(**reference_config["simulation"])
    tight = replace(nominal_settings, **config["tightened_rollout"])
    if tight.rtol >= nominal_settings.rtol or tight.atol >= nominal_settings.atol:
        raise ValueError("The comparison requires tighter relative and absolute tolerances.")
    write_json(output / "config.json", config)
    write_json(output / "input_sha256.json", source)
    models = model_energy_records(read_rows(NOISE / "selected_models.csv"), k)
    write_rows(output / "model_energy.csv", [{name: value for name, value in row.items() if name != "model"}
                                             for row in models.values()])
    rows = evaluate_trajectories(models, k, nominal_settings, tight, noise_config["rollout"], config, output)
    groups, angles = summarize_energy(rows, reference_config["splits"]["test"])
    reference, baseline, time, baseline_traces = baseline_energy(k, config["baseline_figure"])
    for name, values in {
        "trajectory_energy.csv": rows, "group_energy.csv": groups, "angle_energy.csv": angles,
        "reference_energy.csv": reference, "baseline_energy.csv": baseline,
    }.items():
        write_rows(output / name, values)
    plot_sindy_energy(groups, rows, figure_dir)
    plot_baseline_energy(time, baseline_traces, config["baseline_figure"], figure_dir)
    source_paths = [Path(__file__), ROOT / "requirements-lock.txt", ROOT / "lean/Pendulum/Energy.lean",
                    ROOT / "lean/Pendulum/FrozenModels.lean",
                    *sorted((ROOT / "src/pendulum_research").glob("*.py"))]
    write_json(output / "run_metadata.json", {
        "phase": 3, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "physical_k_s2": k, "intended_rollouts": len(rows), "frozen_models": len(models),
        "nominal_completed": sum(row["nominal_status"] == "completed" for row in rows),
        "tight_completed": sum(row["tight_status"] == "completed" for row in rows),
        "status_changes": sum(row["nominal_status"] != row["tight_status"] for row in rows),
        "packages": {name: metadata.version(name) for name in ("numpy", "scipy", "matplotlib")},
        "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in source_paths},
    })
    paths = sorted([*output.iterdir(), *figure_dir.iterdir()])
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.relative_to(ROOT)}\n" for path in paths), encoding="utf-8"
    )
    write_json(output / "run_status.json", {"phase": 3, "status": "completed"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/energy_drift")
    parser.add_argument("--figures", type=Path, default=ROOT / "figures/energy_drift")
    args = parser.parse_args()
    output, figures = args.output.resolve(), args.figures.resolve()
    if not output.is_relative_to(ROOT) or not figures.is_relative_to(ROOT):
        parser.error("Use output paths within this project.")
    if output.exists() or figures.exists() or output.is_relative_to(figures) or figures.is_relative_to(output):
        parser.error("Use two new, separate output directories.")
    output.mkdir(parents=True)
    figures.mkdir(parents=True)
    try:
        run(json.loads((ROOT / "configs/energy.json").read_text()), output, figures)
    except Exception as error:
        write_json(output / "run_status.json", {"phase": 3, "status": "failed", "error": str(error)})
        raise


if __name__ == "__main__":
    main()
