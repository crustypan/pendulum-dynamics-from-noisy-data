#!/usr/bin/env python3
"""Run Phase 1 once and preserve the configuration, fitted models and raw outputs."""

import argparse
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform

import numpy as np

from pendulum_research.data_generation import generate_references, load_config
from pendulum_research.evaluation import angle_coverage, trajectory_metrics
from pendulum_research.models import fit_models
from pendulum_research.physics import (
    Simulation, exact_reference_period, reference_trajectory, relative_energy_drift, simulate,
)
from pendulum_research.visualization import generate_figures

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(config: dict, output: Path, figure_dir: Path):
    settings = Simulation(**config["simulation"])
    k = config["physics"]["gravity_m_s2"] / config["physics"]["length_m"]
    write_json(output / "config.json", config)
    references = generate_references(config)
    reference_rows, verification_rows = [], []
    limits = config["verification"]
    for angle, trajectory in references.items():
        tighter = reference_trajectory(angle, k, replace(settings, rtol=1e-13, atol=1e-15))
        drift = relative_energy_drift(trajectory, k)
        period_error = abs(trajectory.period_s - exact_reference_period(angle, k))
        tolerance_shift = float(np.max(np.abs(trajectory.theta - tighter.theta)))
        if (drift > limits["reference_relative_energy_limit"]
                or period_error > limits["period_absolute_error_limit_s"]
                or tolerance_shift > limits["tolerance_refinement_angle_limit_rad"]):
            raise RuntimeError(f"Reference verification failed at initial angle {angle}.")
        verification_rows.append({
            "angle_deg": angle, "relative_energy_drift": drift,
            "event_period_s": trajectory.period_s,
            "exact_period_s": exact_reference_period(angle, k),
            "period_abs_error_s": period_error, "tighter_tolerance_max_angle_change_rad": tolerance_shift,
        })
        for time, theta, omega in zip(trajectory.time, trajectory.theta, trajectory.omega):
            reference_rows.append({
                "angle_deg": angle, "time_s": float(time),
                "theta_rad": float(theta), "omega_rad_s": float(omega),
            })
    write_csv(output / "reference.csv", reference_rows)
    write_csv(output / "reference_checks.csv", verification_rows)

    fitted = {}
    for training in ("training_A", "training_B"):
        angles = config["splits"][training]
        fitted[training] = fit_models([references[angle].theta for angle in angles], settings.dt_s)
    write_json(output / "models.json", {
        training: {name: {**model.to_dict(), "equation": model.equation}
                   for name, model in models.items()}
        for training, models in fitted.items()
    })

    metrics_rows, prediction_rows = [], []
    for training, models in fitted.items():
        training_angles = config["splits"][training]
        for split, angles in (
            ("training", training_angles),
            ("validation", config["splits"]["validation"]),
            ("test", config["splits"]["test"]),
        ):
            for angle in angles:
                for name, model in models.items():
                    prediction = simulate(model.acceleration, angle, settings)
                    metrics_rows.append({
                        "training_set": training, "model": name, "split": split, "angle_deg": angle,
                        "coverage": "in_sample" if split == "training" else angle_coverage(angle, training_angles),
                        **trajectory_metrics(references[angle], prediction),
                        "parameter_relative_error": abs(model.a - k) / k if name == "M2" else None,
                    })
                    for time, theta, omega in zip(prediction.time, prediction.theta, prediction.omega):
                        prediction_rows.append({
                            "training_set": training, "model": name, "split": split,
                            "angle_deg": angle, "time_s": float(time),
                            "theta_rad": float(theta), "omega_rad_s": float(omega),
                        })
    write_csv(output / "metrics.csv", metrics_rows)
    write_csv(output / "predictions.csv", prediction_rows)
    generate_figures(output, figure_dir)
    sources = sorted(
        [*ROOT.glob("src/**/*.py"), *ROOT.glob("scripts/*.py"), *ROOT.glob("tests/*.py"),
         ROOT / "pyproject.toml", ROOT / "requirements-lock.txt"]
    )
    write_json(output / "run_metadata.json", {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {dist.metadata["Name"]: dist.version for dist in metadata.distributions()},
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
        "config_sha256": hashlib.sha256((output / "config.json").read_bytes()).hexdigest(),
        "training_signal": "Sampled theta only, with a five-point central second derivative",
        "fitting_parameters_have_access_to_reference_k": False,
        "parameter_error_applicability": "M2 only",
        "runtime": {"cpu_quota_fraction_of_one_core": 0.5, "memory_limit_gib": 1,
                    "network": "isolated", "gpu_devices": "excluded"},
        "phase": 1,
    })
    write_json(output / "run_status.json", {"status": "completed", "phase": 1})
    return {
        "reference_trajectories": len(references),
        "fitted_models": sum(len(models) for models in fitted.values()),
        "evaluated_trajectories": len(metrics_rows),
        "max_reference_energy_drift": max(row["relative_energy_drift"] for row in verification_rows),
        "max_period_error_s": max(row["period_abs_error_s"] for row in verification_rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/baseline.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/baseline")
    parser.add_argument("--figures", type=Path, default=ROOT / "figures/baseline")
    args = parser.parse_args()
    config = load_config(args.config)
    output, figure_dir = args.output.resolve(), args.figures.resolve()
    if not output.is_relative_to(ROOT) or not figure_dir.is_relative_to(ROOT):
        parser.error("All outputs must remain within the project.")
    if output.exists() or figure_dir.exists():
        parser.error("Use new output and figure directories to preserve previous runs.")
    output.mkdir(parents=True)
    figure_dir.mkdir(parents=True)
    try:
        summary = run(config, output, figure_dir)
    except Exception as error:
        write_json(output / "run_status.json", {
            "status": "failed", "error_type": type(error).__name__, "message": str(error),
        })
        raise
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
