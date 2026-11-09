"""Check the Phase 5 split, selection, saved trajectories and summary tables."""

import argparse
from collections import Counter, defaultdict
import fcntl
import json
from itertools import product
from statistics import mean, median

import numpy as np
from scipy.special import beta

from experiment import (
    DESIGNS, EVALUATION_FILES, FROZEN_FILES, METHODS, PHASE, ROOT, digest,
    fit_trial, hashes, read_csv, read_frozen, read_json, run_path, verify_hashes, write_json,
)
from pendulum_research.noise import preprocessors
from pendulum_research.noise_study import model_from_record
from pendulum_research.physics import Simulation, reference_trajectory
from weak import weak_design


def check_weak(config):
    dt = config["simulation"]["dt_s"]
    time = Simulation(**config["simulation"]).time_grid()
    p = config["preprocessing"]
    trim = p["trim_per_end"]
    for window, power in product(p["weak_windows"], p["weak_powers"]):
        affine = 0.1 + 0.4 * time
        library, acceleration = weak_design(affine, dt, window, power, trim)
        assert library.shape == (time.size - 2 * trim, 4)
        np.testing.assert_allclose(library[:, 0], affine[trim:-trim], rtol=0, atol=1e-12)
        np.testing.assert_allclose(library[:, 3], 0.4, rtol=0, atol=1e-12)
        np.testing.assert_allclose(acceleration, 0, rtol=0, atol=1e-10)
        constant = np.full(time.size, 0.7)
        library, acceleration = weak_design(constant, dt, window, power, trim)
        np.testing.assert_allclose(library, np.tile([0.7, 0.7**3, np.sin(0.7), 0], (library.shape[0], 1)),
                                   rtol=0, atol=1e-12)
        np.testing.assert_allclose(acceleration, 0, rtol=0, atol=1e-10)
        quadratic = 0.12 - 0.15 * time + 0.3 * time**2
        _, acceleration = weak_design(quadratic, dt, window, power, trim)
        phi = (1 - np.linspace(-1, 1, window)**2)**power
        integral = ((window - 1) * dt / 2) * beta(0.5, power + 1)
        # A linear interpolant has second derivative impulses at each slope jump.
        expected = 0.6 * dt * phi[1:-1].sum() / integral
        np.testing.assert_allclose(acceleration, expected, rtol=0, atol=1e-10)


def check_observations(directory, config):
    settings = Simulation(**config["simulation"])
    splits = config["splits"]
    narrow, wide, validation, test, primary = map(
        set, (splits["narrow"], splits["wide"], splits["validation"], splits["test"], splits["primary"]),
    )
    assert len(narrow) == len(wide) == 4 and len(narrow & wide) == 3
    angles = sorted(narrow | wide | validation)
    assert not (narrow | wide) & validation
    assert not set(angles) & test and primary < test and min(primary) > max(narrow | wide)
    trials = read_csv(directory / "trials.csv")
    expected_trials = [
        (index, float(sigma), seed)
        for index, sigma in enumerate(config["noise_std_deg"])
        for seed in (config["seed"]["noisy_replicates"] if sigma else [config["seed"]["noiseless_replicate"]])
    ]
    assert expected_trials == [(int(row["noise_index"]), float(row["noise_std_deg"]), int(row["seed"])) for row in trials]
    with np.load(directory / "observations.npz") as archive:
        observed = archive["theta_obs_rad"]
        np.testing.assert_array_equal(archive["angle_deg"], angles)
        np.testing.assert_array_equal(archive["trial_index"], np.arange(len(trials)))
        np.testing.assert_array_equal(archive["time_s"], settings.time_grid())
    assert observed.shape == (len(trials), len(angles), settings.time_grid().size)
    truth = np.stack([reference_trajectory(angle, config["physics"]["k_s2"], settings).theta for angle in angles])
    for i, (noise_index, sigma, seed) in enumerate(expected_trials):
        assert int(trials[i]["trial_index"]) == i
        for j, true_angle in enumerate(truth):
            generator = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
                [config["seed"]["master"], noise_index, seed, j],
            )))
            expected = true_angle + generator.normal(0, sigma * np.pi / 180, size=true_angle.shape)
            np.testing.assert_allclose(observed[i, j], expected, atol=1e-11, rtol=1e-11)
    return trials, angles, observed


def check_selection(directory, config, trials, selections):
    grouped = defaultdict(list)
    for row in read_csv(directory / "candidates.csv"):
        grouped[row["case_id"]].append(row)
    expected_cases = {
        (row["trial_index"], design, method)
        for row, design, method in product(trials, DESIGNS, METHODS)
    }
    assert len(selections) == len(expected_cases) == len(grouped)
    assert {(row["trial_index"], row["training_design"], row["method"]) for row in selections} == expected_cases
    p = config["preprocessing"]
    variants = {
        "direct": [(None, None, None)],
        "savgol": [(w, order, None) for w, order in product(p["savgol_windows"], p["savgol_orders"])],
        "weak": [(w, None, power) for w, power in product(p["weak_windows"], p["weak_powers"])],
    }
    validation_angles = set(map(str, config["splits"]["validation"]))
    for selection in selections:
        case = selection["case_id"]
        assert case == f"t{int(selection['trial_index']):02d}-{selection['training_design']}-{selection['method']}"
        grid = grouped[case]
        assert all(
            row[field] == selection[field] for row in grid
            for field in ("trial_index", "noise_std_deg", "noise_index", "seed", "training_design", "method")
        )
        expected_grid = [
            ("" if w is None else str(w), "" if order is None else str(order), "" if power is None else str(power), x)
            for (w, order, power), x in product(variants[selection["method"]], config["stlsq"]["thresholds"])
        ]
        assert [(row["window_samples"], row["polynomial_order"], row["weak_power"], float(row["threshold"]))
                for row in grid] == expected_grid
        assert [int(row["candidate_index"]) for row in grid] == list(range(len(grid)))
        eligible = []
        for row in grid:
            errors = json.loads(row["validation_per_angle_rmse"])
            failures = json.loads(row["validation_failures"])
            assert set(errors) | set(failures) == validation_angles and not set(errors) & set(failures)
            if not failures:
                assert row["validation_status"] == "completed"
                np.testing.assert_allclose(float(row["validation_rmse_rad"]), mean(errors.values()), rtol=0, atol=1e-14)
                eligible.append(row)
            else:
                assert row["validation_status"] == "incomplete" and not row["validation_rmse_rad"]
        assert len(grid) == int(selection["candidate_count"])
        assert len(eligible) == int(selection["valid_candidate_count"])
        chosen = [row for row in grid if row["selected"] == "1"]
        model = model_from_record(selection)
        if eligible:
            best = min(float(row["validation_rmse_rad"]) for row in eligible)
            tie_tolerance = config["validation"]["tie_tolerance_rad"]
            winner = sorted(
                (int(row["term_count"]), float(row["validation_rmse_rad"]), int(row["candidate_index"]))
                for row in eligible if float(row["validation_rmse_rad"]) <= best + tie_tolerance
            )[0][2]
            assert model is not None and chosen == [grid[winner]]
            assert all(selection[key] == value for key, value in grid[winner].items())
        else:
            assert model is None and not chosen
    return sum(map(len, grouped.values()))


def energy_drift(theta, omega, k):
    energy = 0.5 * omega**2 + 2 * k * np.sin(theta / 2)**2
    return float(np.max(np.abs(energy - energy[0])) / energy[0])


def check_tests(directory, config, selected):
    splits = config["splits"]
    k = config["physics"]["k_s2"]
    tests = read_csv(directory / "test_metrics.csv")
    audits = read_csv(directory / "tolerance_audit.csv")
    models = read_csv(directory / "model_metrics.csv")
    assert len(models) == len(selected)
    assert {row["case_id"] for row in models} == set(selected)
    for row in models:
        selection = selected[row["case_id"]]
        assert row["fit_status"] == selection["fit_status"]
        assert row["support"] == selection["support"]
        assert int(row["sine_only"]) == int(row["support"] == "sin_theta")
    expected = {(case, angle) for case, angle in product(selected, splits["test"])}
    assert len(tests) == len(expected)
    assert {(row["case_id"], int(row["angle_deg"])) for row in tests} == expected
    with np.load(directory / "test_reference.npz") as archive:
        angles = archive["angle_deg"]
        time = archive["time_s"]
        true_theta, true_omega = archive["theta_rad"], archive["omega_rad_s"]
    assert list(angles) == splits["test"]
    np.testing.assert_array_equal(time, Simulation(**config["simulation"]).time_grid())
    np.testing.assert_allclose(true_theta[:, 0], np.deg2rad(angles), rtol=0, atol=1e-15)
    np.testing.assert_array_equal(true_omega[:, 0], np.zeros(len(angles)))
    assert all(energy_drift(theta, omega, k) < 1e-8 for theta, omega in zip(true_theta, true_omega))
    with np.load(directory / "test_predictions.npz") as archive:
        pred_theta, pred_omega = archive["theta_rad"], archive["omega_rad_s"]
        np.testing.assert_array_equal(archive["time_s"], time)
        np.testing.assert_array_equal(archive["prediction_index"], np.arange(len(tests)))
    assert pred_theta.shape == pred_omega.shape == (len(tests), len(time))
    by_angle = dict(zip(angles, true_theta))
    primary = {}
    statuses = {"completed", "state_limit", "no_selected_model", "numerical_failure"}
    for i, row in enumerate(tests):
        angle = int(row["angle_deg"])
        scope = "primary" if angle in splits["primary"] else "secondary"
        selection = selected[row["case_id"]]
        assert int(row["prediction_index"]) == i and row["scope"] == scope
        assert all(row[field] == selection[field] for field in ("noise_std_deg", "seed", "training_design", "method"))
        train = splits[row["training_design"]]
        assert row["coverage"] == ("interpolation" if min(train) <= angle <= max(train) else "extrapolation")
        assert row["status"] in statuses
        assert (row["status"] == "no_selected_model") == (selection["fit_status"] != "selected")
        if row["status"] == "completed":
            theta, omega = pred_theta[i], pred_omega[i]
            assert np.isfinite(theta).all() and np.isfinite(omega).all()
            np.testing.assert_allclose([theta[0], omega[0]], [np.deg2rad(angle), 0], rtol=0, atol=1e-15)
            rmse = np.sqrt(np.mean((theta - by_angle[angle])**2))
            np.testing.assert_allclose(
                [float(row["theta_rmse_rad"]), float(row["max_relative_physical_energy_drift"])],
                [rmse, energy_drift(theta, omega, k)], rtol=0, atol=1e-14,
            )
        else:
            assert np.isnan(pred_theta[i]).all() and np.isnan(pred_omega[i]).all()
            assert row["theta_rmse_rad"] == row["max_relative_physical_energy_drift"] == ""
        if scope == "primary":
            primary[row["case_id"], row["angle_deg"]] = row
    assert len(audits) == len(primary)
    assert {(row["case_id"], row["angle_deg"]) for row in audits} == set(primary)
    for audit in audits:
        test = primary[audit["case_id"], audit["angle_deg"]]
        assert audit["nominal_status"] == test["status"] and audit["tight_status"] in statuses
        assert audit["nominal_rmse_rad"] == test["theta_rmse_rad"]
        assert audit["nominal_max_relative_physical_energy_drift"] == test["max_relative_physical_energy_drift"]
        assert bool(audit["tight_rmse_rad"]) == (audit["tight_status"] == "completed")
        assert bool(audit["max_sampled_theta_difference_rad"]) == (
            audit["nominal_status"] == audit["tight_status"] == "completed"
        )
    return tests, len(audits)


def check_report(directory, tests):
    pool = "pooled_noisy"
    prim = [row for row in tests if row["scope"] == "primary"]
    groups = read_csv(directory / "group_summary.csv")
    assert len(groups) == 30 and len(read_csv(directory / "by_release.csv")) == 90
    for group in groups:
        level = group["noise_level_deg"]
        chosen = [
            row for row in prim
            if row["training_design"] == group["training_design"] and row["method"] == group["method"]
            and (float(row["noise_std_deg"]) > 0 if level == pool else row["noise_std_deg"] == level)
        ]
        status = Counter(row["status"] for row in chosen)
        assert len(chosen) == int(group["planned_rollouts"])
        assert status["state_limit"] == int(group["state_limit_rollouts"])
        assert status["completed"] == int(group["completed_rollouts"])
        assert len(chosen) - status["state_limit"] - status["completed"] == int(group["other_incomplete_rollouts"])
        completed = [float(row["theta_rmse_rad"]) for row in chosen if row["status"] == "completed"]
        if completed:
            np.testing.assert_allclose(float(group["median_theta_rmse_rad_completed"]), median(completed),
                                       rtol=0, atol=1e-14)
        else:
            assert not group["median_theta_rmse_rad_completed"]

    keyed = {
        (row["noise_std_deg"], row["seed"], row["angle_deg"], row["training_design"], row["method"]): row
        for row in prim
    }
    contrasts = read_csv(directory / "paired_contrasts.csv")
    assert len(contrasts) == 135
    for row in contrasts:
        level, metric = row["noise_level_deg"], row["metric"]
        sums = defaultdict(list)
        for key, left in keyed.items():
            noise, seed, angle, design, method = key
            if design != row["left_design"] or method != row["left_method"]:
                continue
            if not (float(noise) > 0 if level == pool else noise == level):
                continue
            right = keyed[noise, seed, angle, row["right_design"], row["right_method"]]
            if metric == "theta_rmse_rad":
                if not left["status"] == right["status"] == "completed":
                    continue
                diff = float(left["theta_rmse_rad"]) - float(right["theta_rmse_rad"])
            else:
                status = {"guard_rate": "state_limit", "completion_rate": "completed"}[metric]
                diff = int(left["status"] == status) - int(right["status"] == status)
            sums[noise, seed].append(diff)
        assert len(sums) == int(row["matched_seeds"]) and sum(map(len, sums.values())) == int(row["matched_rollouts"])
        if sums:
            observed = float(row["estimate_left_minus_right"])
            np.testing.assert_allclose(observed, mean(mean(values) for values in sums.values()), rtol=0, atol=1e-14)
        else:
            assert not row["estimate_left_minus_right"]
        assert bool(row["bootstrap_lower_95"]) == bool(row["bootstrap_upper_95"]) == (len(sums) > 1)
        if len(sums) > 1:
            assert float(row["bootstrap_lower_95"]) <= float(row["bootstrap_upper_95"])


def replay_trial(config, trial, angles, observed, saved_selection, directory):
    prep = preprocessors(config["preprocessing"])
    methods = {method: tuple(row for row in prep if row.method == method) for method in METHODS[:-1]}
    index = int(trial["trial_index"])
    fields = ("trial_index", "noise_index", "seed")
    info = {key: int(value) if key in fields else float(value) for key, value in trial.items()}
    fitted, grid = fit_trial(info, dict(zip(angles, observed[index])), config, Simulation(**config["simulation"]), methods)
    old = [row for row in read_csv(directory / "candidates.csv") if int(row["trial_index"]) == index]
    assert len(old) == len(grid)
    for expected, actual in zip(old, grid):
        assert expected["case_id"] == actual["case_id"] and int(expected["candidate_index"]) == actual["candidate_index"]
        assert expected["support"] == actual["support"] and int(expected["selected"]) == actual["selected"]
        if actual["validation_rmse_rad"] is not None:
            np.testing.assert_allclose(float(expected["validation_rmse_rad"]), actual["validation_rmse_rad"],
                                       rtol=1e-9, atol=1e-10)
    for row in fitted:
        expected = saved_selection[row["case_id"]]
        assert row["fit_status"] == expected["fit_status"]
        if row["fit_status"] == "selected":
            assert row["candidate_index"] == int(expected["candidate_index"])
            assert model_from_record(row).support == model_from_record(expected).support
            np.testing.assert_allclose(model_from_record(row).coefficients, model_from_record(expected).coefficients,
                                       rtol=1e-9, atol=1e-10)


def verify(directory, replay):
    frozen, config = read_frozen(directory)
    assert set(frozen["file_sha256"]) == set(FROZEN_FILES)
    fit_inputs = read_json(directory / "fit_inputs.json")
    assert digest(PHASE / "config.json") == fit_inputs["config_source_sha256"]
    evaluation = read_json(directory / "evaluation_manifest.json")
    assert digest(directory / "selection_frozen.json") == evaluation["selection_frozen_sha256"]
    assert set(evaluation["file_sha256"]) == set(EVALUATION_FILES)
    verify_hashes(directory, evaluation["file_sha256"])
    check_weak(config)
    trials, angles, observed = check_observations(directory, config)
    selections = read_csv(directory / "selected_models.csv")
    candidates = check_selection(directory, config, trials, selections)
    selected = {row["case_id"]: row for row in selections}
    tests, audit_count = check_tests(directory, config, selected)
    check_report(directory, tests)
    assert (len(trials), len(selected), candidates, len(tests), audit_count) == (61, 366, 18544, 1098, 732)
    if replay is not None:
        replay_trial(config, trials[replay], angles, observed, selected, directory)
    figure_files = tuple(f"figures/{name}.png" for name in ("benchmark_outcomes", "paired_effects", "heldout_example"))
    for name in figure_files:
        assert (directory / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    write_json(directory / "verification.json", {
        "status": "passed",
        "paired_trials": len(trials), "model_cases": len(selected), "candidates": candidates,
        "all_test_rollouts": len(tests), "tolerance_audit_rows": audit_count,
        "weak_operators_checked": 9, "replayed_trial_index": replay,
        "report_source_sha256": hashes(ROOT, ("phase5/report.py", "phase5/verify.py")),
        "report_artifact_sha256": hashes(directory, (
            "group_summary.csv", "by_release.csv", "paired_contrasts.csv", "numerical_summary.json", *figure_files,
        )),
    })
    print("Verified 366 validation decisions, 1,098 test rows, 732 audit rows and all three figures.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default="phase5/results/main")
    parser.add_argument("--replay-trial", type=int, choices=range(61), metavar="0–60")
    args = parser.parse_args()
    directory = run_path(args.run_dir)
    (directory / ".tmp").mkdir(exist_ok=True, mode=0o700)
    with (directory / ".tmp" / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify(directory, args.replay_trial)


if __name__ == "__main__":
    main()
