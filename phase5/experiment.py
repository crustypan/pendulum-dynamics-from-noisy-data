"""Fit the frozen Phase 5 designs and evaluate fresh release angles."""

import argparse
import csv
from dataclasses import replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
from platform import python_version

import numpy as np
import scipy

from pendulum_research.noise import observe_theta, preprocessors
from pendulum_research.noise_study import (
    evaluate_test_angles, fit_diagnostics, model_from_record, rmse, select_case, validation_score,
)
from pendulum_research.physics import Simulation, reference_trajectory, relative_energy_drift
from pendulum_research.sindy import COEFFICIENT_COLUMNS, fit_stlsq
from weak import weak_design

PHASE = Path(__file__).resolve().parent
ROOT = PHASE.parent
DESIGNS = ("narrow", "wide")
METHODS = ("direct", "savgol", "weak")
TRIAL_FIELDS = ("trial_index", "noise_std_deg", "noise_index", "seed")
CASE_FIELDS = ("case_id", *TRIAL_FIELDS, "training_design", "method")
CANDIDATE_FIELDS = (
    "candidate_index", "window_samples", "polynomial_order", "weak_power", "threshold",
    "support", "term_count", *COEFFICIENT_COLUMNS, "equation", "train_acceleration_rmse_rad_s2",
    "corr_theta_cubic", "corr_theta_sine", "corr_cubic_sine", "scaled_condition_number",
    "validation_status", "validation_rmse_rad", "validation_per_angle_rmse",
    "validation_failures", "selected",
)
SELECTION_FIELDS = (*CASE_FIELDS, "fit_status", "candidate_count", "valid_candidate_count", *CANDIDATE_FIELDS)
INPUT_FILES = ("fit_inputs.json", "config.json", "observations.npz", "trials.csv")
FROZEN_FILES = (*INPUT_FILES, "candidates.csv", "selected_models.csv")
EVALUATION_FILES = (
    "test_metrics.csv", "model_metrics.csv", "test_reference.npz", "test_predictions.npz", "tolerance_audit.csv",
)
SOURCE_FILES = (
    "phase5/PROTOCOL.md", "phase5/experiment.py", "phase5/weak.py", "phase5/run_isolated.py",
    "requirements-lock.txt",
    *(f"src/pendulum_research/{name}.py" for name in (
        "__init__", "evaluation", "noise", "noise_study", "physics", "sindy",
    )),
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def hashes(directory, files):
    return {name: digest(directory / name) for name in files}


def verify_hashes(directory, expected):
    for name, value in expected.items():
        if digest(directory / name) != value:
            raise ValueError(f"SHA-256 mismatch for {directory / name}")


def scratch_path(path):
    scratch = path.parent / ".tmp"
    scratch.mkdir(exist_ok=True, mode=0o700)
    return scratch / (path.name + ".writing")


def write_json(path, payload):
    scratch = scratch_path(path)
    scratch.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    scratch.replace(path)


def write_csv(path, fields, records):
    scratch = scratch_path(path)
    with scratch.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    scratch.replace(path)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_npz(path, **arrays):
    scratch = scratch_path(path)
    with scratch.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    scratch.replace(path)


def run_path(argument):
    archive = PHASE / "results"
    requested = (ROOT / argument).resolve()
    if archive.resolve() != archive or requested.parent != archive or requested.name.startswith("."):
        raise ValueError("A run directory must be a direct child of phase5/results.")
    return requested


def check_splits(config):
    splits = config["splits"]
    narrow, wide = (set(splits[name]) for name in DESIGNS)
    train = narrow | wide
    validation = set(splits["validation"])
    test = set(splits["test"])
    primary = set(splits["primary"])
    if (
        len(narrow) != len(wide) or len(narrow) != 4
        or len(splits["narrow"]) != len(narrow) or len(splits["wide"]) != len(wide)
        or train & validation or train & test or validation & test
        or not primary <= test or min(primary) <= max(train)
        or config["physics"]["initial_omega_rad_s"] != 0
    ):
        raise ValueError("The configured split or release conditions violate the protocol.")
    return sorted(train | validation)


def trial_plan(config):
    trials = []
    for noise_index, sigma in enumerate(config["noise_std_deg"]):
        seeds = config["seed"]["noisy_replicates"] if sigma else [config["seed"]["noiseless_replicate"]]
        for seed in seeds:
            trials.append(dict(zip(TRIAL_FIELDS, (len(trials), sigma, noise_index, seed))))
    return trials


def select_weak_case(training, validation, settings, config):
    """Apply the v1 STLSQ and validation criterion to the weak library."""
    preprocess = config["preprocessing"]
    grid = []
    scores = {}
    for window in preprocess["weak_windows"]:
        for power in preprocess["weak_powers"]:
            blocks = [
                weak_design(theta, settings.dt_s, window, power, preprocess["trim_per_end"])
                for theta in training.values()
            ]
            design = np.vstack([block[0] for block in blocks])
            target = np.concatenate([block[1] for block in blocks])
            diagnostics = fit_diagnostics(design)
            for threshold in config["stlsq"]["thresholds"]:
                model = fit_stlsq(design, target, threshold, config["stlsq"]["ridge_alpha"])
                if model.coefficients not in scores:
                    scores[model.coefficients] = validation_score(model, validation, settings, config["rollout"])
                grid.append({
                    "candidate_index": len(grid), "window_samples": window, "polynomial_order": None,
                    "weak_power": power, "threshold": threshold,
                    "support": "+".join(model.support) or "empty", "term_count": len(model.support),
                    **dict(zip(COEFFICIENT_COLUMNS, model.coefficients)), "equation": model.equation,
                    "train_acceleration_rmse_rad_s2": rmse(design @ model.coefficients, target),
                    **diagnostics, **scores[model.coefficients], "selected": 0,
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
        selected = dict.fromkeys(CANDIDATE_FIELDS)
    selected.update(
        fit_status="selected" if eligible else "no_valid_validation",
        candidate_count=len(grid), valid_candidate_count=len(eligible),
    )
    return selected, grid


def make_observations(directory, config, angles, trials, settings):
    k = config["physics"]["k_s2"]
    truth = {angle: reference_trajectory(angle, k, settings).theta for angle in angles}
    arrays = np.array([
        [
            observe_theta(
                truth[angle], trial["noise_std_deg"], config["seed"]["master"],
                trial["noise_index"], trial["seed"], index,
            )
            for index, angle in enumerate(angles)
        ]
        for trial in trials
    ])
    write_npz(
        directory / "observations.npz", theta_obs_rad=arrays, angle_deg=angles,
        time_s=settings.time_grid(), trial_index=np.arange(len(trials)),
    )
    write_csv(directory / "trials.csv", TRIAL_FIELDS, trials)


def fit_trial(trial, observations, config, settings, preprocess):
    splits = config["splits"]
    validation = {angle: observations[angle] for angle in splits["validation"]}
    selected_models = []
    candidates = []
    for design in DESIGNS:
        training = {angle: observations[angle] for angle in splits[design]}
        for method in METHODS:
            case_id = f"t{trial['trial_index']:02d}-{design}-{method}"
            keys = {"case_id": case_id, **trial, "training_design": design, "method": method}
            if method == "weak":
                selected, grid = select_weak_case(training, validation, settings, config)
            else:
                selected, grid = select_case(training, validation, settings, preprocess[method], config)
            selected_models.append({**keys, **selected})
            candidates.extend({**keys, **row} for row in grid)
    return selected_models, candidates


def fit(directory):
    if (directory / "selection_frozen.json").exists():
        read_frozen(directory)
        print("Selection already frozen and verified.", flush=True)
        return

    config = read_json(PHASE / "config.json")
    angles = check_splits(config)
    trials = trial_plan(config)
    settings = Simulation(**config["simulation"])
    inputs = {
        "source_sha256": hashes(ROOT, SOURCE_FILES),
        "config_source_sha256": digest(PHASE / "config.json"),
        "runtime": {"python": python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "observation_angles_deg": angles,
    }
    if (directory / "fit_inputs.json").exists():
        saved = read_json(directory / "fit_inputs.json")
        if any(saved[key] != value for key, value in inputs.items()):
            raise ValueError("Fit inputs changed. Use a fresh run directory.")
        verify_hashes(directory, saved["file_sha256"])
    else:
        write_json(directory / "config.json", config)
        make_observations(directory, config, angles, trials, settings)
        write_json(directory / "fit_inputs.json", {
            **inputs, "file_sha256": hashes(directory, INPUT_FILES[1:]),
        })

    with np.load(directory / "observations.npz") as archive:
        measurements = archive["theta_obs_rad"]
    variants = preprocessors(config["preprocessing"])
    preprocess = {method: tuple(p for p in variants if p.method == method) for method in METHODS[:-1]}
    checkpoints = directory / ".tmp" / "fit"
    checkpoints.mkdir(exist_ok=True, mode=0o700)
    fingerprint = digest(directory / "fit_inputs.json")
    selected_models = []
    candidates = []
    for trial in trials:
        index = trial["trial_index"]
        checkpoint = checkpoints / f"{index:02d}.json"
        if checkpoint.exists():
            saved = read_json(checkpoint)
            if saved["fit_inputs_sha256"] != fingerprint:
                raise ValueError(f"Unexpected checkpoint fingerprint in {checkpoint}")
            selected, grid = saved["selected_models"], saved["candidates"]
        else:
            observations = dict(zip(angles, measurements[index]))
            selected, grid = fit_trial(trial, observations, config, settings, preprocess)
            write_json(checkpoint, {
                "fit_inputs_sha256": fingerprint, "selected_models": selected, "candidates": grid,
            })
        selected_models.extend(selected)
        candidates.extend(grid)
        if index == 0 or (index + 1) % 5 == 0 or index + 1 == len(trials):
            print(f"Fitted {index + 1}/{len(trials)} paired trials ({len(candidates)} candidates).", flush=True)

    verify_hashes(ROOT, inputs["source_sha256"])
    write_csv(directory / "candidates.csv", (*CASE_FIELDS, *CANDIDATE_FIELDS), candidates)
    write_csv(directory / "selected_models.csv", SELECTION_FIELDS, selected_models)
    write_json(directory / "selection_frozen.json", {
        "file_sha256": hashes(directory, FROZEN_FILES), "test_reference_generated": False,
        "planned_model_cases": len(selected_models), "candidate_count": len(candidates),
        "selected_model_cases": sum(row["fit_status"] == "selected" for row in selected_models),
    })
    print("Selection frozen. No test reference was generated by fit.", flush=True)


def read_frozen(directory):
    manifest = read_json(directory / "selection_frozen.json")
    if manifest["test_reference_generated"] is not False:
        raise ValueError("The selection stage must not generate test references.")
    verify_hashes(directory, manifest["file_sha256"])
    verify_hashes(ROOT, read_json(directory / "fit_inputs.json")["source_sha256"])
    return manifest, read_json(directory / "config.json")


def evaluate(directory):
    frozen, config = read_frozen(directory)
    if (directory / "evaluation_manifest.json").exists():
        verify_hashes(directory, read_json(directory / "evaluation_manifest.json")["file_sha256"])
        print("Evaluation already archived and verified.", flush=True)
        return
    settings = Simulation(**config["simulation"])
    tight_settings = replace(settings, **config["evaluation"]["tightened_rollout"])
    limits = config["rollout"]
    k = config["physics"]["k_s2"]
    splits = config["splits"]
    references = {angle: reference_trajectory(angle, k, settings) for angle in splits["test"]}
    primary_references = {angle: references[angle] for angle in splits["primary"]}
    time = settings.time_grid()
    write_npz(
        directory / "test_reference.npz", angle_deg=list(references), time_s=time,
        theta_rad=np.stack([trajectory.theta for trajectory in references.values()]),
        omega_rad_s=np.stack([trajectory.omega for trajectory in references.values()]),
    )
    models = read_csv(directory / "selected_models.csv")
    theta = np.full((len(models) * len(references), len(time)), np.nan)
    omega = np.full_like(theta, np.nan)
    tests = []
    model_metrics = []
    tolerance_audit = []
    for index, selected in enumerate(models):
        keys = {field: selected[field] for field in CASE_FIELDS}
        model = model_from_record(selected)
        exact_support = model is not None and model.support == ("sin_theta",)
        model_metrics.append({
            **keys, "fit_status": selected["fit_status"], "support": selected["support"],
            "sine_only": int(exact_support), "c_sin_theta": selected["c_sin_theta"],
            "sine_coefficient_relative_error": abs(float(selected["c_sin_theta"]) + k) / k if model else None,
            "abs_corr_theta_sine": (
                abs(float(selected["corr_theta_sine"])) if selected["corr_theta_sine"] else None
            ),
            "scaled_condition_number": selected["scaled_condition_number"],
        })
        train_angles = splits[selected["training_design"]]
        nominal = evaluate_test_angles(model, references, train_angles, settings, limits)
        tighter = evaluate_test_angles(model, primary_references, train_angles, tight_settings, limits)
        tight_by_angle = {row["angle_deg"]: (row, prediction) for row, prediction in tighter}
        for metrics, prediction in nominal:
            row_index = len(tests)
            angle = metrics["angle_deg"]
            scope = "primary" if angle in primary_references else "secondary"
            drift = None
            if prediction is not None:
                theta[row_index] = prediction.theta
                omega[row_index] = prediction.omega
                drift = relative_energy_drift(prediction, k)
            tests.append({
                **keys, "prediction_index": row_index, "scope": scope, **metrics,
                "max_relative_physical_energy_drift": drift,
            })
            if scope == "primary":
                tight_metrics, tight_prediction = tight_by_angle[angle]
                both_completed = prediction is not None and tight_prediction is not None
                tolerance_audit.append({
                    **keys, "angle_deg": angle, "nominal_status": metrics["status"],
                    "tight_status": tight_metrics["status"],
                    "nominal_rmse_rad": metrics["theta_rmse_rad"],
                    "tight_rmse_rad": tight_metrics["theta_rmse_rad"],
                    "nominal_max_relative_physical_energy_drift": drift,
                    "tight_max_relative_physical_energy_drift": (
                        relative_energy_drift(tight_prediction, k) if tight_prediction is not None else None
                    ),
                    "max_sampled_theta_difference_rad": (
                        float(np.max(np.abs(prediction.theta - tight_prediction.theta))) if both_completed else None
                    ),
                })
        if (index + 1) % 60 == 0 or index + 1 == len(models):
            print(f"Evaluated {index + 1}/{len(models)} model cases.", flush=True)

    write_csv(directory / "test_metrics.csv", tuple(tests[0]), tests)
    write_csv(directory / "model_metrics.csv", tuple(model_metrics[0]), model_metrics)
    write_csv(directory / "tolerance_audit.csv", tuple(tolerance_audit[0]), tolerance_audit)
    write_npz(
        directory / "test_predictions.npz", time_s=time,
        prediction_index=np.arange(len(tests)), theta_rad=theta, omega_rad_s=omega,
    )
    write_json(directory / "evaluation_manifest.json", {
        "selection_frozen_sha256": digest(directory / "selection_frozen.json"),
        "file_sha256": hashes(directory, EVALUATION_FILES),
        "model_cases": frozen["planned_model_cases"], "planned_test_rollouts": len(tests),
        "primary_rollouts": len(tolerance_audit),
        "reference_max_relative_physical_energy_drift": {
            str(angle): relative_energy_drift(trajectory, k) for angle, trajectory in references.items()
        },
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("fit", "evaluate"))
    parser.add_argument("--run-dir", default="phase5/results/main")
    args = parser.parse_args()
    directory = run_path(args.run_dir)
    if args.stage == "evaluate" and not (directory / "selection_frozen.json").is_file():
        parser.error("Run fit to completion before evaluating the test set.")
    scratch = directory / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (scratch / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (fit if args.stage == "fit" else evaluate)(directory)


if __name__ == "__main__":
    main()
