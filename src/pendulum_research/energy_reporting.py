"""Summarize sampled physical energy drift and render the experiment figures."""

from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pendulum_research.energy import relative_change
from pendulum_research.noise_reporting import GROUP_FIELDS, grouped, stats


def drift_stats(values: list[float]) -> dict:
    return {
        **stats(values, "drift"),
        "drift_median": float(np.median(values)) if values else None,
        "drift_p90": float(np.quantile(values, 0.9)) if values else None,
        "drift_max": max(values, default=None),
    }


def summarize_energy(rows: list[dict], test_angles: list[float]) -> tuple[list[dict], list[dict]]:
    by_angle, by_group = [], []
    for keys, group in grouped(rows, (*GROUP_FIELDS, "angle_deg", "coverage")).items():
        values = [row["nominal_drift"] for row in group if row["nominal_drift"] is not None]
        by_angle.append({
            **dict(zip((*GROUP_FIELDS, "angle_deg", "coverage"), keys)),
            "intended_rollouts": len(group), "completed_rollouts": len(values),
            **drift_stats(values),
        })
    for keys, group in grouped(rows, GROUP_FIELDS).items():
        by_model = grouped(group, ("model_id",))
        completed_means = []
        for model in by_model.values():
            if len(model) != len(test_angles) or {row["angle_deg"] for row in model} != set(test_angles):
                raise ValueError("Each model must have exactly one record for each test angle.")
            if all(row["nominal_status"] == "completed" for row in model):
                completed_means.append(mean(row["nominal_drift"] for row in model))
        by_group.append({
            **dict(zip(GROUP_FIELDS, keys)), "intended_repetitions": len(by_model),
            "completed_repetitions": len(completed_means),
            "completed_repetition_fraction": len(completed_means) / len(by_model),
            **drift_stats(completed_means),
        })
    return by_group, by_angle


def plot_sindy_energy(groups: list[dict], trajectories: list[dict], figure_dir: Path):
    figure, axes = plt.subplots(2, 2, figsize=(10.8, 7.9))
    styles = {"training_A": ("#2166ac", "o"), "training_B": ("#af4d20", "s")}
    methods = {"direct": "P1 central", "savgol": "P2 Savitzky–Golay"}
    for (training, method), rows in grouped(groups, ("training_set", "method")).items():
        rows.sort(key=lambda row: row["noise_std_deg"])
        x = [row["noise_std_deg"] for row in rows]
        color, marker = styles[training]
        style = {"color": color, "marker": marker, "linestyle": "--" if method == "direct" else "-"}
        label = f"{training.replace('_', ' ').title()}, {methods[method]}"
        axes[0, 0].plot(x, [row["drift_median"] for row in rows], label=label, **style)
        axes[0, 1].plot(x, [row["completed_repetition_fraction"] for row in rows], **style)
        for axis in axes[0]:
            axis.set_xticks(x)
            axis.set_xlabel("Angle noise SD (deg)")
    axes[0, 0].set(title="Median drift among complete repetitions", ylabel="Mean sampled D_E over three angles",
                  yscale="log")
    axes[0, 1].set(title="Repetitions completing all test angles", ylabel="Fraction of repetitions", ylim=(-0.04, 1.04))

    complete = [row for row in trajectories if row["nominal_drift"] is not None]
    for exact, label, color in ((1, "Sine only", "#1b7837"), (0, "Additional terms", "#762a83")):
        selected = [row for row in complete if row["sine_only"] == exact]
        axes[1, 0].scatter([row["theta_rmse_rad"] for row in selected],
                           [row["nominal_drift"] for row in selected],
                           s=13, alpha=0.45, color=color, label=label, edgecolors="none")
    axes[1, 0].set(title="Trajectory error and physical energy drift", xlabel="Test angle RMSE (rad)",
                  ylabel="Sampled D_E", xscale="log", yscale="log")
    axes[1, 0].legend(frameon=False, fontsize=8)

    paired = [row for row in complete if row["tight_shared_drift"] is not None]
    x = [row["nominal_drift"] for row in paired]
    y = [row["tight_shared_drift"] for row in paired]
    if paired:
        lo, hi = min(x + y), max(x + y)
        if lo > 0:
            axes[1, 1].plot([lo, hi], [lo, hi], color="#333333", linewidth=0.9, linestyle="--")
    axes[1, 1].scatter(x, y, color="#008080", s=10, alpha=0.38, edgecolors="none")
    axes[1, 1].set(title="Solver agreement on shared samples", xlabel="Nominal sampled D_E",
                  ylabel="Tightened sampled D_E", xscale="log", yscale="log")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.suptitle("Physical energy drift of the frozen SINDy models", y=0.988)
    figure.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.949), ncol=2, frameon=False)
    for axis in axes.flat:
        axis.grid(alpha=0.23)
    figure.tight_layout(rect=(0, 0.02, 1, 0.87))
    figure.savefig(figure_dir / "physical_energy_drift.png", dpi=180)
    plt.close(figure)


def plot_baseline_energy(time: np.ndarray, traces: dict, settings: dict, figure_dir: Path):
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))
    colors = {"Reference": "#222222", "M1": "#d95f02", "M2": "#1b9e77", "M3": "#7570b3"}
    for model, (physical, own) in traces.items():
        for axis, energy in zip(axes, (physical, own)):
            error = np.abs(relative_change(energy))
            axis.plot(time, np.where(error > 0, error, np.nan), color=colors[model], label=model)
    for axis, title in zip(axes, ("Reference physical energy", "Each model's own energy")):
        axis.set(title=title, xlabel="Time (s)", ylabel="Absolute relative energy change", yscale="log")
        axis.grid(alpha=0.23)
    handles, labels = axes[0].get_legend_handles_labels()
    training = settings["training_set"].replace("_", " ").title()
    angle = settings["angle_deg"]
    figure.suptitle(f"Energy comparison at {angle}° with {training}", y=0.987)
    figure.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.935), ncol=4, frameon=False)
    figure.tight_layout(rect=(0, 0.01, 1, 0.85))
    figure.savefig(figure_dir / "baseline_conservation.png", dpi=180)
    plt.close(figure)
