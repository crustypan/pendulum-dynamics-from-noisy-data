"""Audit the frozen selection, observations and reported test metrics."""

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

from pendulum_research.evaluation import angle_coverage
from pendulum_research.noise import observe_theta
from pendulum_research.noise_study import model_from_record
from pendulum_research.physics import exact_reference_period
from pendulum_research.sindy import COEFFICIENT_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def verify_selection(output: Path, config: dict, splits: dict) -> dict:
    selected = {row["model_id"]: row for row in rows(output / "selected_models.csv")}
    freeze = json.loads((output / "selection_frozen.json").read_text())
    assert freeze["stage"] == "validation_complete" and freeze["test_reference_generated"] is False
    for field, filename in (
        ("selected_models_sha256", "selected_models.csv"),
        ("validation_grid_sha256", "validation_grid.csv.gz"),
        ("noise_config_sha256", "config.json"),
        ("reference_config_sha256", "reference_config.json"),
    ):
        assert freeze[field] == digest(output / filename)
    candidates = defaultdict(list)
    with gzip.open(output / "validation_grid.csv.gz", "rt", newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            candidates[row["model_id"]].append(row)
    assert candidates.keys() == selected.keys()
    validation_angles = {float(angle) for angle in splits["validation"]}
    for model_id, record in selected.items():
        grid = candidates[model_id]
        grid_indices = [int(row["candidate_index"]) for row in grid]
        assert grid_indices == list(range(int(record["candidate_count"])))
        settings = [(None, None)] if record["method"] == "direct" else [
            (window, order) for window in config["preprocessing"]["savgol_windows"]
            for order in config["preprocessing"]["savgol_orders"]
        ]
        expected_settings = [(window, order, threshold) for window, order in settings
                             for threshold in config["stlsq"]["thresholds"]]
        actual_settings = [
            (int(row["window_samples"]) if row["window_samples"] else None,
             int(row["polynomial_order"]) if row["polynomial_order"] else None, float(row["threshold"]))
            for row in grid
        ]
        assert actual_settings == expected_settings
        eligible = [row for row in grid if row["validation_status"] == "completed"]
        chosen = [row for row in grid if row["selected"] == "1"]
        assert len(eligible) == int(record["valid_candidate_count"])
        for row in grid:
            errors = json.loads(row["validation_per_angle_rmse"])
            failures = json.loads(row["validation_failures"])
            assert set(map(float, errors)).isdisjoint(map(float, failures))
            assert set(map(float, (*errors, *failures))) == validation_angles
            if not failures:
                np.testing.assert_allclose(float(row["validation_rmse_rad"]), np.mean(list(errors.values())),
                                           rtol=1e-13, atol=1e-15)
        if not eligible:
            assert record["fit_status"] == "no_valid_validation" and not chosen
            continue
        best = min(float(row["validation_rmse_rad"]) for row in eligible)
        expected = min(
            (row for row in eligible
             if float(row["validation_rmse_rad"]) <= best + config["validation"]["tie_tolerance_rad"]),
            key=lambda row: (int(row["term_count"]), float(row["validation_rmse_rad"]), int(row["candidate_index"])),
        )
        assert chosen == [expected] and record["fit_status"] == "selected"
        for name in ("candidate_index", "window_samples", "polynomial_order", "threshold",
                     "support", "equation", "validation_rmse_rad", *COEFFICIENT_COLUMNS):
            assert record[name] == expected[name]
        model_from_record(record)
    return selected


def verify_observations(output: Path, config: dict, splits: dict, reference: dict) -> list[dict]:
    trials = rows(output / "trials.csv")
    expected = [
        (noise_index, float(noise), seed)
        for noise_index, noise in enumerate(config["noise_std_deg"])
        for seed in ([config["seed"]["noiseless_replicate"]] if noise == 0 else config["seed"]["noisy_replicates"])
    ]
    assert [(int(row["noise_index"]), float(row["noise_std_deg"]), int(row["seed"]))
            for row in trials] == expected
    angles = sorted(set(splits["validation"]).union(splits["training_A"], splits["training_B"]))
    with np.load(output / "observations.npz", allow_pickle=False) as observed:
        np.testing.assert_array_equal(observed["angle_deg"], angles)
        actual = observed["theta_obs_rad"]
        assert actual.shape == (len(expected), len(angles), len(observed["time_s"]))
        np.testing.assert_array_equal(observed["time_s"], next(iter(reference.values()))[0])
        for trial_id, (noise_index, noise, seed) in enumerate(expected):
            assert int(trials[trial_id]["trial_id"]) == trial_id
            for index, angle in enumerate(angles):
                regenerated = observe_theta(reference[angle][1], noise, config["seed"]["master"],
                                            noise_index, seed, index)
                np.testing.assert_array_equal(actual[trial_id, index], regenerated)
    return trials


def verify_tests(output: Path, splits: dict, reference: dict, k: float, selected: dict) -> tuple[int, int]:
    tests = rows(output / "test_metrics.csv")
    expected_keys = {(model_id, float(angle)) for model_id in selected for angle in splits["test"]}
    assert len(tests) == len(expected_keys)
    assert {(row["model_id"], float(row["angle_deg"])) for row in tests} == expected_keys
    with np.load(output / "test_predictions.npz", allow_pickle=False) as stored:
        time, predicted, speed = stored["time_s"], stored["theta_rad"], stored["omega_rad_s"]
    assert predicted.shape == speed.shape == (len(tests), len(time))
    complete = 0
    by_model = defaultdict(list)
    for index, row in enumerate(tests):
        assert int(row["prediction_index"]) == index
        angle = float(row["angle_deg"])
        assert row["coverage"] == angle_coverage(angle, splits[row["training_set"]])
        reference_time, theta = reference[angle]
        np.testing.assert_array_equal(time, reference_time)
        np.testing.assert_allclose(float(row["reference_period_s"]), exact_reference_period(angle, k),
                                   rtol=0, atol=1e-8)
        by_model[row["model_id"]].append(row)
        if row["status"] == "completed":
            assert np.isfinite(predicted[index]).all() and np.isfinite(speed[index]).all()
            np.testing.assert_allclose(predicted[index, 0], np.deg2rad(angle), atol=1e-14, rtol=0)
            assert speed[index, 0] == 0
            actual = np.sqrt(np.mean((predicted[index] - theta)**2))
            np.testing.assert_allclose(actual, float(row["theta_rmse_rad"]), rtol=1e-13, atol=1e-15)
            if row["predicted_period_s"]:
                period = float(row["reference_period_s"])
                error = abs(float(row["predicted_period_s"]) - period) / period
                np.testing.assert_allclose(error, float(row["period_relative_error"]), rtol=1e-13, atol=1e-15)
            else:
                assert not row["period_relative_error"]
            complete += 1
        else:
            assert row["status"] in {"state_limit", "numerical_failure", "no_selected_model"}
            assert np.isnan(predicted[index]).all() and np.isnan(speed[index]).all()
            assert not row["theta_rmse_rad"] and not row["period_relative_error"]

    models = rows(output / "model_metrics.csv")
    assert {row["model_id"] for row in models} == selected.keys() and len(models) == len(selected)
    groups = defaultdict(list)
    for row in models:
        model = model_from_record(selected[row["model_id"]])
        support = model.support if model else ()
        assert int(row["exact_sine_support"]) == (support == ("sin_theta",))
        if "sin_theta" in support:
            error = abs(model.coefficients[2] + k) / k
            np.testing.assert_allclose(error, float(row["sine_coefficient_relative_error"]), atol=1e-15, rtol=1e-13)
        else:
            assert not row["sine_coefficient_relative_error"]
        errors = [float(item["theta_rmse_rad"]) for item in by_model[row["model_id"]] if item["status"] == "completed"]
        assert int(row["test_angles_completed"]) == len(errors)
        assert bool(int(row["all_test_angles_completed"])) == (len(errors) == len(splits["test"]))
        if len(errors) == len(splits["test"]):
            np.testing.assert_allclose(np.mean(errors), float(row["test_rmse_rad"]), atol=1e-15, rtol=1e-13)
        else:
            assert not row["test_rmse_rad"]
        groups[(row["noise_std_deg"], row["training_set"], row["method"])].append(row)

    summary = rows(output / "summary.csv")
    assert len(summary) == len(groups)
    for row in summary:
        records = groups[(row["noise_std_deg"], row["training_set"], row["method"])]
        assert int(row["repetitions"]) == len(records)
        assert int(row["exact_support_count"]) == sum(int(item["exact_sine_support"]) for item in records)
        errors = [float(item["test_rmse_rad"]) for item in records if item["test_rmse_rad"]]
        assert int(row["test_rmse_rad_n"]) == len(errors) == int(row["all_test_angles_completed_count"])
        if errors:
            np.testing.assert_allclose(np.mean(errors), float(row["test_rmse_rad_mean"]), atol=1e-15, rtol=1e-13)
        if len(errors) > 1:
            np.testing.assert_allclose(np.std(errors, ddof=1), float(row["test_rmse_rad_sd"]), atol=1e-15, rtol=1e-13)
    return len(tests), complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results/noise_sindy")
    output = parser.parse_args().results.resolve()
    if not output.is_relative_to(ROOT):
        parser.error("Saved results must belong to this project.")
    assert json.loads((output / "run_status.json").read_text()) == {"phase": 2, "status": "completed"}
    for line in (output / "SHA256SUMS").read_text().splitlines():
        expected, relative = line.split("  ", 1)
        path = (ROOT / relative).resolve()
        assert path.is_relative_to(ROOT) and digest(path) == expected, relative
    metadata = json.loads((output / "run_metadata.json").read_text())
    for relative, expected in metadata["source_sha256"].items():
        assert digest(ROOT / relative) == expected, relative
    assert digest(output / "selection_frozen.json") == metadata["validation_freeze_sha256"]

    config = json.loads((output / "config.json").read_text())
    baseline = json.loads((output / "reference_config.json").read_text())
    splits = baseline["splits"]
    k = baseline["physics"]["gravity_m_s2"] / baseline["physics"]["length_m"]
    with np.load(output / "reference.npz", allow_pickle=False) as clean:
        time = clean["time_s"]
        reference = {float(angle): (time, theta) for angle, theta in zip(clean["angle_deg"], clean["theta_rad"])}
    selected = verify_selection(output, config, splits)
    trials = verify_observations(output, config, splits, reference)
    expected_cases = {(int(trial["trial_id"]), training, method) for trial in trials
                      for training in ("training_A", "training_B") for method in ("direct", "savgol")}
    assert len(selected) == len(expected_cases)
    assert {(int(row["trial_id"]), row["training_set"], row["method"])
            for row in selected.values()} == expected_cases
    tested, complete = verify_tests(output, splits, reference, k, selected)
    print(json.dumps({
        "status": "verified", "regenerated_observation_trials": len(trials),
        "frozen_model_cases": len(selected),
        "validation_candidates_audited": sum(int(row["candidate_count"]) for row in selected.values()),
        "test_rollouts_audited": tested,
        "completed_test_rollouts": complete, "artifact_checksums": "passed",
        "source_checksums": "passed", "summary_statistics": "passed",
    }, indent=2))


if __name__ == "__main__":
    main()
