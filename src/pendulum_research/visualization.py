"""Figures derived from saved CSV files, with English labels and physical units."""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"M1": "#bc4343", "M2": "#007f7c", "M3": "#7350a2"}


def generate_figures(results_dir: Path, figure_dir: Path):
    with (results_dir / "reference.csv").open(newline="") as stream:
        reference = list(csv.DictReader(stream))
    with (results_dir / "predictions.csv").open(newline="") as stream:
        predictions = list(csv.DictReader(stream))
    with (results_dir / "metrics.csv").open(newline="") as stream:
        metrics = list(csv.DictReader(stream))
    figure_dir.mkdir(parents=True, exist_ok=True)
    angles = sorted({float(row["angle_deg"]) for row in metrics if row["split"] == "test"})
    training_sets = ("training_A", "training_B")
    figure, axes = plt.subplots(2, len(angles), figsize=(13, 6.8), sharex=True, squeeze=False)
    for row_index, training in enumerate(training_sets):
        for column_index, angle in enumerate(angles):
            axis = axes[row_index, column_index]
            truth = [row for row in reference if float(row["angle_deg"]) == angle]
            axis.plot([float(row["time_s"]) for row in truth], [float(row["theta_rad"]) for row in truth],
                      color="#202a35", linewidth=1.6, label="Reference")
            for model in COLORS:
                values = [row for row in predictions if row["training_set"] == training
                          and row["model"] == model and float(row["angle_deg"]) == angle
                          and row["split"] == "test"]
                axis.plot([float(row["time_s"]) for row in values],
                          [float(row["theta_rad"]) for row in values], color=COLORS[model],
                          linestyle={"M1": "--", "M2": ":", "M3": "-."}[model], linewidth=1.2, label=model)
            axis.set_title(f"{training.replace('_', ' ').title()}, initial angle {angle:g} deg")
            axis.set_ylabel("Angle (rad)")
            axis.set_xlabel("Time (s)")
            axis.grid(alpha=0.2)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.suptitle("Noiseless held-out trajectories", y=0.99, fontsize=14)
    figure.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.955),
                  ncol=4, frameon=False)
    figure.tight_layout(rect=(0, 0, 1, 0.90))
    figure.savefig(figure_dir / "trajectory_comparison.png", dpi=180, bbox_inches="tight")
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
    for axis, training in zip(axes, training_sets):
        for model in COLORS:
            values = sorted((row for row in metrics if row["training_set"] == training
                             and row["model"] == model and row["split"] == "test"),
                            key=lambda row: float(row["angle_deg"]))
            axis.plot([float(row["angle_deg"]) for row in values],
                      [float(row["theta_rmse_rad"]) for row in values],
                      color=COLORS[model], marker="o", label=model)
        axis.set_title(training.replace("_", " ").title())
        axis.set_xlabel("Initial angle (deg)")
        axis.set_yscale("log")
        axis.grid(alpha=0.2, which="both")
    axes[0].set_ylabel("Trajectory RMSE (rad)")
    axes[1].legend(frameon=False)
    figure.suptitle("Generalization on held-out initial conditions")
    figure.tight_layout()
    figure.savefig(figure_dir / "test_rmse.png", dpi=180)
    plt.close(figure)
