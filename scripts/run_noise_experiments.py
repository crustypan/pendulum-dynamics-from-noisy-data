#!/usr/bin/env python3
"""Fit and freeze noisy SINDy models, then evaluate the held-out trajectories."""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
from importlib import metadata
import json
from pathlib import Path
from statistics import mean

import numpy as np

from pendulum_research.data_generation import load_config
from pendulum_research.noise import Preprocessing, observe_theta, preprocessors
from pendulum_research.noise_reporting import DERIVATIVE_FIELDS, paired_errors, plot_phase2, summarize, write_rows
from pendulum_research.noise_study import derivative_errors, evaluate_test_angles, model_from_record, select_case
from pendulum_research.physics import Simulation, reference_trajectory

ROOT = Path(__file__).resolve().parents[1]
TRAINING = ("training_A", "training_B")
METHODS = ("direct", "savgol")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_file(path: Path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_noise_config(path: Path) -> tuple[dict, dict]:
    config = json.loads(path.read_text())
    levels = config["noise_std_deg"]
    thresholds = config["stlsq"]["thresholds"]
    windows = config["preprocessing"]["savgol_windows"]
    orders = config["preprocessing"]["savgol_orders"]
    trim = config["preprocessing"]["trim_per_end"]
    seeds = config["seed"]["noisy_replicates"]
    if config["phase"] != 2 or not levels or levels[0] != 0 or sorted(set(levels)) != levels:
        raise ValueError("Expected Phase 2 and distinct increasing noise levels beginning at zero.")
    if not np.isfinite(levels).all() or not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Noise levels must be finite and noisy seeds must be distinct.")
    if any(type(seed) is not int or seed < 0 for seed in (*seeds, config["seed"]["master"],
                                                         config["seed"]["noiseless_replicate"])):
        raise ValueError("Seeds must be nonnegative integers.")
    if (not thresholds or not np.isfinite(thresholds).all() or min(thresholds) < 0
            or len(set(thresholds)) != len(thresholds)):
        raise ValueError("Expected distinct, finite, nonnegative STLSQ thresholds.")
    alpha = config["stlsq"]["ridge_alpha"]
    tie = config["validation"]["tie_tolerance_rad"]
    if not np.isfinite([alpha, tie]).all() or min(alpha, tie) < 0:
        raise ValueError("The ridge penalty and score tie tolerance must be finite and nonnegative.")
    if (not windows or not orders or type(trim) is not int or trim < 1
            or any(type(w) is not int or w % 2 == 0 or not 3 <= w <= 2 * trim + 1 for w in windows)
            or any(type(order) is not int or not 2 <= order < min(windows) for order in orders)):
        raise ValueError("Savitzky–Golay settings must fit the common interior.")
    limits = list(config["rollout"].values())
    if not limits or not np.isfinite(limits).all() or min(limits) <= 0:
        raise ValueError("Rollout limits must be positive and finite.")
    if (config["seed"]["bit_generator"] != "PCG64"
            or config["validation"]["score"] != "mean_rollout_angle_rmse_against_noisy_validation"):
        raise ValueError("Unsupported random generator or validation score.")
    reference_path = (ROOT / config["reference_config"]).resolve()
    if not reference_path.is_relative_to(ROOT):
        raise ValueError("The reference configuration must belong to the project.")
    baseline = load_config(reference_path)
    if Simulation(**baseline["simulation"]).time_grid().size <= 2 * trim:
        raise ValueError("The common interior must contain observation samples.")
    return config, baseline


def select_all(config: dict, splits: dict, references: dict, settings: Simulation, output: Path) -> np.ndarray:
    observation_angles = sorted(references)
    methods = {
        method: tuple(item for item in preprocessors(config["preprocessing"]) if item.method == method)
        for method in METHODS
    }
    trials = [
        (noise_index, sigma, seed)
        for noise_index, sigma in enumerate(config["noise_std_deg"])
        for seed in ([config["seed"]["noiseless_replicate"]] if sigma == 0 else config["seed"]["noisy_replicates"])
    ]
    selected_rows, trial_rows, observations = [], [], []
    with gzip.open(output / "validation_grid.csv.gz", "xt", newline="", encoding="utf-8") as stream:
        grid_writer = None
        for trial_id, (noise_index, sigma, seed) in enumerate(trials):
            observed = {
                angle: observe_theta(references[angle].theta, sigma, config["seed"]["master"],
                                     noise_index, seed, angle_index)
                for angle_index, angle in enumerate(observation_angles)
            }
            observations.append(np.stack(list(observed.values())))
            identity = {"trial_id": trial_id, "noise_index": noise_index, "noise_std_deg": sigma, "seed": seed}
            trial_rows.append(identity)
            validation = {angle: observed[angle] for angle in splits["validation"]}
            for training in TRAINING:
                training_data = {angle: observed[angle] for angle in splits[training]}
                for method, variants in methods.items():
                    case = {**identity, "training_set": training, "method": method,
                            "model_id": f"trial{trial_id:03d}_{training[-1]}_{method}"}
                    selected, grid = select_case(training_data, validation, settings, variants, config)
                    selected_rows.append({**case, **selected})
                    if grid_writer is None:
                        grid_writer = csv.DictWriter(stream, fieldnames=[*case, *grid[0]])
                        grid_writer.writeheader()
                    grid_writer.writerows({**case, **row} for row in grid)
            if (trial_id + 1) % 5 == 0 or trial_id + 1 == len(trials):
                stream.flush()
                print(json.dumps({"stage": "validation_selection", "completed_trials": trial_id + 1,
                                  "total_trials": len(trials), "noise_std_deg": sigma}), flush=True)

    data = np.stack(observations)
    write_rows(output / "trials.csv", trial_rows)
    np.savez_compressed(output / "observations.npz", angle_deg=observation_angles,
                        time_s=settings.time_grid(), theta_obs_rad=data)
    write_rows(output / "selected_models.csv", selected_rows)
    json_file(output / "selection_frozen.json", {
        "stage": "validation_complete",
        "selected_models_sha256": digest(output / "selected_models.csv"),
        "validation_grid_sha256": digest(output / "validation_grid.csv.gz"),
        "noise_config_sha256": digest(output / "config.json"),
        "reference_config_sha256": digest(output / "reference_config.json"),
        "test_reference_generated": False,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    return data


def evaluate_all(
    config: dict, splits: dict, observed: np.ndarray, fit_references: dict, test_references: dict,
    settings: Simulation, k: float, output: Path,
) -> tuple[list[dict], list[dict], list[dict]]:
    selected_rows = read_rows(output / "selected_models.csv")
    observation_index = {angle: index for index, angle in enumerate(sorted(fit_references))}
    test_rows, models, derivatives = [], [], []
    shape = (len(selected_rows) * len(test_references), settings.time_grid().size)
    prediction_theta = np.full(shape, np.nan)
    prediction_omega = np.full(shape, np.nan)
    for selected in selected_rows:
        trial_id = int(selected["trial_id"])
        training, method = selected["training_set"], selected["method"]
        identity = {
            "model_id": selected["model_id"], "trial_id": trial_id, "seed": int(selected["seed"]),
            "noise_std_deg": float(selected["noise_std_deg"]), "training_set": training, "method": method,
        }
        model = model_from_record(selected)
        evaluations = evaluate_test_angles(model, test_references, splits[training], settings, config["rollout"])
        completed = 0
        for row, prediction in evaluations:
            index = len(test_rows)
            test_rows.append({**identity, "prediction_index": index, **row})
            if prediction is not None:
                prediction_theta[index] = prediction.theta
                prediction_omega[index] = prediction.omega
                completed += 1

        support = model.support if model else ()
        exact = support == ("sin_theta",)
        sine_error = abs(model.coefficients[2] + k) / k if "sin_theta" in support else None
        optional_metrics = (
            "train_acceleration_rmse_rad_s2", "validation_rmse_rad", "corr_theta_cubic",
            "corr_theta_sine", "corr_cubic_sine", "scaled_condition_number",
        )
        models.append({
            **identity,
            "fit_status": selected["fit_status"], "support": selected["support"] if model else "no_selected_model",
            "term_count": len(support) if model else None,
            "exact_sine_support": int(exact),
            "sine_coefficient_relative_error": sine_error,
            "exact_sine_coefficient_relative_error": sine_error if exact else None,
            "test_angles_completed": completed,
            "all_test_angles_completed": int(completed == len(test_references)),
            "test_rmse_rad": mean(row["theta_rmse_rad"] for row, _ in evaluations)
                             if completed == len(test_references) else None,
            **{field: float(selected[field]) if selected[field] else None for field in optional_metrics},
        })
        prep = Preprocessing(method, int(selected["window_samples"]) if selected["window_samples"] else None,
                             int(selected["polynomial_order"]) if selected["polynomial_order"] else None)
        for angle in splits["validation"]:
            errors = (
                derivative_errors(prep, observed[trial_id, observation_index[angle]], fit_references[angle],
                                  k, settings.dt_s, config["preprocessing"]["trim_per_end"])
                if model is not None else dict.fromkeys(DERIVATIVE_FIELDS)
            )
            derivatives.append({**identity, "angle_deg": angle, "status": selected["fit_status"], **errors})
    np.savez_compressed(output / "test_predictions.npz", time_s=settings.time_grid(),
                        theta_rad=prediction_theta, omega_rad_s=prediction_omega)
    return models, test_rows, derivatives


def run(config: dict, baseline: dict, output: Path, figures: Path):
    json_file(output / "config.json", config)
    json_file(output / "reference_config.json", baseline)
    settings = Simulation(**baseline["simulation"])
    k = baseline["physics"]["gravity_m_s2"] / baseline["physics"]["length_m"]
    splits = baseline["splits"]
    fit_angles = sorted(set(splits["validation"]).union(*(splits[name] for name in TRAINING)))
    fit_references = {angle: reference_trajectory(angle, k, settings) for angle in fit_angles}

    observed = select_all(config, splits, fit_references, settings, output)
    frozen = json.loads((output / "selection_frozen.json").read_text())
    assert frozen["selected_models_sha256"] == digest(output / "selected_models.csv")
    print(json.dumps({"stage": "selection_frozen", "observed_trials": observed.shape[0]}), flush=True)
    test_references = {angle: reference_trajectory(angle, k, settings) for angle in splits["test"]}
    all_references = {**fit_references, **test_references}
    reference_angles = sorted(all_references)
    np.savez_compressed(output / "reference.npz", angle_deg=reference_angles, time_s=settings.time_grid(),
                        theta_rad=np.stack([all_references[angle].theta for angle in reference_angles]),
                        omega_rad_s=np.stack([all_references[angle].omega for angle in reference_angles]))
    models, tests, derivatives = evaluate_all(config, splits, observed, fit_references, test_references,
                                               settings, k, output)
    summary, support_frequencies, by_angle = summarize(models, tests, derivatives)
    tables = {
        "model_metrics.csv": models, "test_metrics.csv": tests, "derivative_metrics.csv": derivatives,
        "summary.csv": summary, "support_frequencies.csv": support_frequencies,
        "test_summary_by_angle.csv": by_angle, "paired_comparisons.csv": paired_errors(models),
    }
    for name, rows in tables.items():
        write_rows(output / name, rows)
    plot_phase2(output / "summary.csv", figures)
    sources = sorted([
        *ROOT.glob("src/pendulum_research/*.py"), ROOT / "scripts/run_noise_experiments.py",
        ROOT / "requirements-lock.txt",
    ])
    json_file(output / "run_metadata.json", {
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": 2,
        "packages": {name: metadata.version(name) for name in ("numpy", "scipy", "matplotlib", "pytest")},
        "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in sources},
        "validation_freeze_sha256": digest(output / "selection_frozen.json"),
        "reference_trajectories": len(reference_angles),
        "intended_models": len(models), "selected_models": sum(row["fit_status"] == "selected" for row in models),
        "test_rollouts": len(tests), "test_rollouts_completed": sum(row["status"] == "completed" for row in tests),
        "derivative_cases": len(derivatives),
        "derivative_checks": sum(row["status"] == "selected" for row in derivatives),
        "runtime": {"cpu_quota_fraction_of_one_core": 0.5, "memory_limit_gib": 1, "network": "isolated"},
    })
    artifacts = sorted([*output.iterdir(), *figures.iterdir()])
    (output / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.relative_to(ROOT)}\n" for path in artifacts),
        encoding="utf-8",
    )
    json_file(output / "run_status.json", {"phase": 2, "status": "completed"})
    print(json.dumps({"stage": "completed", "model_cases": len(models), "test_rollouts": len(tests),
                      "completed_test_rollouts": sum(row["status"] == "completed" for row in tests)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/noise.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/noise_sindy")
    parser.add_argument("--figures", type=Path, default=ROOT / "figures/noise_sindy")
    args = parser.parse_args()
    config_path, output, figures = (path.resolve() for path in (args.config, args.output, args.figures))
    if not all(path.is_relative_to(ROOT) for path in (config_path, output, figures)):
        parser.error("Use paths within the project.")
    if output.is_relative_to(figures) or figures.is_relative_to(output):
        parser.error("Use two separate output and figure directories.")
    if output.exists() or figures.exists():
        parser.error("Use new output and figure directories to preserve previous runs.")
    config, baseline = load_noise_config(config_path)
    output.mkdir(parents=True)
    figures.mkdir(parents=True)
    try:
        run(config, baseline, output, figures)
    except Exception as error:
        json_file(output / "run_status.json", {
            "phase": 2, "status": "failed", "error_type": type(error).__name__, "message": str(error),
        })
        raise


if __name__ == "__main__":
    main()
