"""Summarize the frozen Phase 5 evaluation and regenerate publication figures."""

import argparse
from collections import Counter, defaultdict
import fcntl
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np

from experiment import (
    DESIGNS, METHODS, digest, read_csv, read_frozen, read_json, run_path, scratch_path,
    verify_hashes, write_csv, write_json,
)
from pendulum_research.physics import physical_energy

METHOD_LABELS = {"direct": "Direct", "savgol": "Savitzky–Golay", "weak": "Weak form"}
STYLE = {
    "direct": {"color": "#B24A00", "marker": "o", "linestyle": "--"},
    "savgol": {"color": "#2163A2", "marker": "s", "linestyle": "-"},
    "weak": {"color": "#138170", "marker": "^", "linestyle": "-."},
}
OUTCOMES = ("guard_rate", "completion_rate", "theta_rmse_rad")
NOISY_POOL = "pooled_noisy"


def levels(config):
    return [(str(noise), [str(noise)]) for noise in config["noise_std_deg"]] + [
        (NOISY_POOL, [str(noise) for noise in config["noise_std_deg"] if noise]),
    ]


def optional_median(rows, field):
    values = [float(row[field]) for row in rows if row[field] != ""]
    return median(values) if values else None


def group_summary(models, rollouts, config):
    group_rows = []
    release_rows = []
    for level, included in levels(config):
        for design in DESIGNS:
            for method in METHODS:
                model_group = [
                    row for row in models
                    if row["training_design"] == design and row["method"] == method
                    and row["noise_std_deg"] in included
                ]
                case_ids = {row["case_id"] for row in model_group}
                tests = [row for row in rollouts if row["case_id"] in case_ids]
                key = {"noise_level_deg": level, "training_design": design, "method": method}
                primary = [row for row in tests if row["scope"] == "primary"]
                exact = sum(int(row["sine_only"]) for row in model_group)
                group_rows.append({
                    **key, "model_cases": len(model_group),
                    "selected_models": sum(row["fit_status"] == "selected" for row in model_group),
                    "sine_only_models": exact, "sine_only_rate": exact / len(model_group),
                    "median_sine_coefficient_relative_error_selected": optional_median(
                        model_group, "sine_coefficient_relative_error",
                    ),
                    "median_abs_corr_theta_sine_selected": optional_median(model_group, "abs_corr_theta_sine"),
                    "median_scaled_condition_number_selected": optional_median(model_group, "scaled_condition_number"),
                    **rollout_summary(primary),
                })
                for angle in config["splits"]["test"]:
                    at_angle = [row for row in tests if float(row["angle_deg"]) == angle]
                    release_rows.append({
                        **key, "angle_deg": angle, "scope": at_angle[0]["scope"],
                        "coverage": at_angle[0]["coverage"], **rollout_summary(at_angle),
                    })
    return group_rows, release_rows


def rollout_summary(rows):
    statuses = Counter(row["status"] for row in rows)
    complete = [row for row in rows if row["status"] == "completed"]
    n = len(rows)
    other = n - len(complete) - statuses["state_limit"]
    return {
        "planned_rollouts": n, "state_limit_rollouts": statuses["state_limit"],
        "other_incomplete_rollouts": other, "numerical_failure_rollouts": statuses["numerical_failure"],
        "no_model_rollouts": statuses["no_selected_model"], "completed_rollouts": len(complete),
        "guard_rate": statuses["state_limit"] / n, "other_incomplete_rate": other / n,
        "completion_rate": len(complete) / n,
        "median_theta_rmse_rad_completed": optional_median(complete, "theta_rmse_rad"),
        "median_max_relative_energy_drift_completed": optional_median(complete, "max_relative_physical_energy_drift"),
    }


def comparison_plan():
    return [
        ("training_design", ("wide", method), ("narrow", method), f"Wide − narrow  ·  {METHOD_LABELS[method]}")
        for method in METHODS
    ] + [
        ("method", (design, left), (design, right),
         f"{METHOD_LABELS[left]} − {METHOD_LABELS[right]}  ·  {design}")
        for design in DESIGNS
        for left, right in (("savgol", "direct"), ("weak", "direct"), ("weak", "savgol"))
    ]


def differences(left, right):
    yield "guard_rate", int(left["status"] == "state_limit") - int(right["status"] == "state_limit")
    left_complete = left["status"] == "completed"
    right_complete = right["status"] == "completed"
    yield "completion_rate", int(left_complete) - int(right_complete)
    if left_complete and right_complete:
        yield "theta_rmse_rad", float(left["theta_rmse_rad"]) - float(right["theta_rmse_rad"])


def bootstrap(strata, rng, repetitions):
    count = sum(len(values) for values in strata.values())
    if count == 0:
        return None, None, None
    average = sum(sum(values) for values in strata.values()) / count
    if count == 1:
        return average, None, None
    resampled = np.zeros(repetitions)
    for values in strata.values():
        resampled += rng.choice(values, size=(repetitions, len(values)), replace=True).sum(axis=1)
    lower, upper = np.quantile(resampled / count, [0.025, 0.975])
    return average, float(lower), float(upper)


def paired_contrasts(rollouts, config):
    matches = defaultdict(dict)
    for row in rollouts:
        if row["scope"] == "primary":
            match = (row["noise_std_deg"], row["seed"], row["angle_deg"])
            matches[match][(row["training_design"], row["method"])] = row
    settings = config["evaluation"]
    rng = np.random.default_rng(settings["bootstrap_seed"])
    results = []
    for level, included in levels(config):
        for comparison, left, right, label in comparison_plan():
            per_seed = {outcome: defaultdict(list) for outcome in OUTCOMES}
            for (noise, seed, _angle), group in matches.items():
                if noise in included:
                    for outcome, difference in differences(group[left], group[right]):
                        per_seed[outcome][noise, seed].append(difference)
            for outcome, by_seed in per_seed.items():
                strata = defaultdict(list)
                for (noise, _seed), values in by_seed.items():
                    strata[noise].append(float(np.mean(values)))
                effect, lower, upper = bootstrap(strata, rng, settings["bootstrap_replicates"])
                results.append({
                    "noise_level_deg": level, "comparison": comparison, "label": label,
                    "left_design": left[0], "left_method": left[1],
                    "right_design": right[0], "right_method": right[1], "metric": outcome,
                    "estimate_left_minus_right": effect, "bootstrap_lower_95": lower, "bootstrap_upper_95": upper,
                    "matched_seeds": len(by_seed), "matched_rollouts": sum(map(len, by_seed.values())),
                })
    return results


def numerical_summary(audit, manifest):
    shared = [row for row in audit if row["nominal_status"] == row["tight_status"] == "completed"]
    return {
        "primary_rollouts_rechecked": len(audit),
        "status_changes": sum(row["nominal_status"] != row["tight_status"] for row in audit),
        "completed_at_both_tolerances": len(shared),
        "max_absolute_theta_rmse_change_rad": max(
            abs(float(row["nominal_rmse_rad"]) - float(row["tight_rmse_rad"])) for row in shared
        ) if shared else None,
        "max_absolute_relative_energy_drift_change": max(
            abs(float(row["nominal_max_relative_physical_energy_drift"])
                - float(row["tight_max_relative_physical_energy_drift"])) for row in shared
        ) if shared else None,
        "max_sampled_theta_difference_rad": max(
            float(row["max_sampled_theta_difference_rad"]) for row in shared
        ) if shared else None,
        "reference_max_relative_physical_energy_drift": manifest["reference_max_relative_physical_energy_drift"],
    }


def save_figure(fig, path):
    temp = scratch_path(path)
    fig.savefig(temp, dpi=180, format="png", facecolor="white")
    temp.replace(path)
    plt.close(fig)


def plot_outcomes(groups, config, path):
    fig, axes = plt.subplots(2, 2, sharex=True, sharey=True, figsize=(10, 7.1), layout="constrained")
    tick_labels = [str(noise) for noise in config["noise_std_deg"]]
    x = np.arange(len(tick_labels))
    by_group = {(row["training_design"], row["method"], row["noise_level_deg"]): row for row in groups}
    for column, design in enumerate(DESIGNS):
        for row, (field, ylabel) in enumerate((
            ("guard_rate", "State-limit stops"), ("sine_only_rate", "Sine-only support"),
        )):
            ax = axes[row, column]
            for method in METHODS:
                values = [by_group[design, method, noise][field] for noise in tick_labels]
                ax.plot(x, values, label=METHOD_LABELS[method], linewidth=2, markersize=6, **STYLE[method])
            ax.grid(axis="y", color="#D6DEE6", linewidth=0.8)
            ax.set_axisbelow(True)
            ax.set_ylim(-0.06, 1.06)
            ax.set_yticks(np.linspace(0, 1, 5), labels=["0%", "25%", "50%", "75%", "100%"])
            ax.set_xticks(x, labels=tick_labels)
            if column == 0:
                ax.set_ylabel(ylabel)
            if row == 0:
                angles = "°, ".join(map(str, config["splits"][design])) + "°"
                ax.set_title(f"{design.title()}  ·  {angles}", loc="left", fontsize=11)
            else:
                ax.set_xlabel("Angle noise SD (deg)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncols=3, frameon=False)
    fig.suptitle(
        "Angle coverage and noise treatment\n"
        "State limits at 80° and 95°  ·  1 clean trial, 20 trials per noisy level",
        fontsize=14,
    )
    save_figure(fig, path)


def plot_contrasts(contrasts, path):
    rows = [row for row in contrasts if row["noise_level_deg"] == NOISY_POOL]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.7), sharey=True)
    fig.subplots_adjust(left=0.29, right=0.90, top=0.82, bottom=0.14, wspace=0.22)
    fig.suptitle("Paired effects across 0.5°, 2° and 5° noise", y=0.97, fontsize=15)
    fig.text(0.5, 0.90, "Primary tests at 80° and 95°  ·  dots show means, bars show 95% paired bootstrap intervals",
             ha="center", fontsize=10)
    for ax, metric, label, multiplier in zip(
        axes, ("guard_rate", "theta_rmse_rad"),
        ("State-limit rate difference (pp)", "Angle RMSE difference (rad)"), (100, 1),
    ):
        selected = [row for row in rows if row["metric"] == metric]
        y = np.arange(len(selected))
        ax.axvline(0, color="#8593A0", linewidth=1)
        for boundary in (2.5, 5.5):
            ax.axhline(boundary, color="#D6DEE6", linewidth=0.8)
        ax.set_yticks(y, labels=[row["label"] for row in selected], fontsize=9)
        ax.set_ylim(len(selected) - 0.5, -0.5)
        ax.set_xlabel(label, fontsize=10)
        for index, row in enumerate(selected):
            estimate = row["estimate_left_minus_right"]
            lower = row["bootstrap_lower_95"]
            upper = row["bootstrap_upper_95"]
            color = ("#2163A2", "#B24A00", "#138170")[index // 3]
            if estimate is not None:
                ax.plot(estimate * multiplier, index, "o", color=color, zorder=3)
            if lower is not None:
                ax.hlines(index, lower * multiplier, upper * multiplier, color=color, linewidth=2)
            if metric == "theta_rmse_rad":
                ax.text(
                    1.03, index, f"{row['matched_seeds']}/{row['matched_rollouts']}",
                    va="center", transform=ax.get_yaxis_transform(), fontsize=8, color="#37475A",
                )
        if metric == "theta_rmse_rad":
            ax.text(1.03, 1.02, "Seeds/paths", transform=ax.transAxes, fontsize=8, color="#37475A")
        else:
            ax.set_title("60 paired seeds, 120 paths", fontsize=10)
    fig.text(0.5, 0.04, "Each contrast is the left group minus the right group. RMSE requires both paths to finish.",
             ha="center", fontsize=9)
    save_figure(fig, path)


def plot_example(directory, tests, config, path):
    # A fixed noisy trial and the largest primary release, regardless of outcomes.
    noise = 2
    seed = 0
    angle = max(config["splits"]["primary"])
    k = config["physics"]["k_s2"]
    selected = {
        (row["training_design"], row["method"]): row for row in tests
        if float(row["noise_std_deg"]) == noise and int(row["seed"]) == seed and float(row["angle_deg"]) == angle
    }
    with np.load(directory / "test_reference.npz") as archive:
        time = archive["time_s"]
        index = int(np.flatnonzero(archive["angle_deg"] == angle)[0])
        true_theta = archive["theta_rad"][index]
        true_omega = archive["omega_rad_s"][index]
    with np.load(directory / "test_predictions.npz") as archive:
        pred_theta = archive["theta_rad"]
        pred_omega = archive["omega_rad_s"]
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 7), sharex=True, sharey="row", layout="constrained")
    for column, design in enumerate(DESIGNS):
        angle_ax, energy_ax = axes[:, column]
        for ax in (angle_ax, energy_ax):
            ax.grid(color="#D6DEE6", linewidth=0.7)
            ax.set_axisbelow(True)
        angle_ax.set_title(f"{design.title()} training", loc="left", fontsize=11)
        angle_ax.plot(time, np.rad2deg(true_theta), color="#1D2835", label="Reference", linewidth=1.2)
        true_energy = physical_energy(true_theta, true_omega, k)
        energy_ax.plot(time, (true_energy - true_energy[0]) / true_energy[0], color="#1D2835", linewidth=1.2)
        for method in METHODS:
            row = selected[design, method]
            color = STYLE[method]["color"]
            line = STYLE[method]["linestyle"]
            label = METHOD_LABELS[method]
            if row["status"] == "completed":
                index = int(row["prediction_index"])
                angle_ax.plot(time, np.rad2deg(pred_theta[index]), color=color, linestyle=line, label=label)
                energy = physical_energy(pred_theta[index], pred_omega[index], k)
                energy_ax.plot(time, (energy - energy[0]) / energy[0], color=color, linestyle=line)
            else:
                angle_ax.plot([], [], color=color, linestyle=":", label=f"{label} ({row['status'].replace('_', ' ')})")
        angle_ax.legend(loc="upper right", fontsize=8, ncols=2, framealpha=0.95)
        energy_ax.set_xlabel("Time (s)")
        energy_ax.set_yscale("symlog", linthresh=0.01, linscale=0.7)
        energy_ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    axes[0, 0].set_ylabel("Angle (deg)")
    axes[1, 0].set_ylabel("Physical energy change\n(symmetric log scale)")
    fig.suptitle(f"Example at a new {angle}° release\nAngle noise SD {noise}°  ·  seed {seed}  ·  10-second trajectories",
                 fontsize=14)
    save_figure(fig, path)


def report(directory):
    _frozen, config = read_frozen(directory)
    manifest = read_json(directory / "evaluation_manifest.json")
    if digest(directory / "selection_frozen.json") != manifest["selection_frozen_sha256"]:
        raise ValueError("Evaluation does not match the frozen selection.")
    verify_hashes(directory, manifest["file_sha256"])
    models = read_csv(directory / "model_metrics.csv")
    tests = read_csv(directory / "test_metrics.csv")
    groups, releases = group_summary(models, tests, config)
    contrasts = paired_contrasts(tests, config)
    audit = numerical_summary(read_csv(directory / "tolerance_audit.csv"), manifest)
    for name, rows in (("group_summary", groups), ("by_release", releases), ("paired_contrasts", contrasts)):
        write_csv(directory / f"{name}.csv", tuple(rows[0]), rows)
    write_json(directory / "numerical_summary.json", audit)
    figures = directory / "figures"
    figures.mkdir(exist_ok=True)
    plot_outcomes(groups, config, figures / "benchmark_outcomes.png")
    plot_contrasts(contrasts, figures / "paired_effects.png")
    plot_example(directory, tests, config, figures / "heldout_example.png")
    print("Wrote group and paired tables, numerical summary and three figures.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default="phase5/results/main")
    args = parser.parse_args()
    directory = run_path(args.run_dir)
    (directory / ".tmp").mkdir(exist_ok=True, mode=0o700)
    with (directory / ".tmp" / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report(directory)


if __name__ == "__main__":
    main()
