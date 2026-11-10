"""Draw separate physics and result figures from archived predictions.

Run from the repository root with the pinned project Python environment.
The example selection matches phase5/report.py: 95 degrees, 2 degrees of
angle noise, seed 0, wide training. It is not selected for its outcome.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "phase5/results/main"
PHYSICS_OUTPUT = ROOT / "figures/overview/pendulum_reference.png"
RESULT_OUTPUT = ROOT / "figures/overview/heldout_95deg.png"
K = 9.81
RELEASE = 95
NOISE = 2.0
SEED = 0
DESIGN = "wide"
COLORS = {"reference": "#1D2835", "direct": "#C45A0A", "savgol": "#3468A5", "weak": "#008B80"}
LABELS = {"reference": "Reference", "direct": "Direct difference", "savgol": "Local polynomial", "weak": "Weak form"}
STYLES = {"reference": "-", "direct": "--", "savgol": ":", "weak": "-."}


def energy(theta: np.ndarray, omega: np.ndarray) -> np.ndarray:
    return omega**2 / 2 + K * (1 - np.cos(theta))


def main() -> None:
    with (RUN / "test_metrics.csv").open(newline="") as stream:
        cases = list(csv.DictReader(stream))
    selected = {
        row["method"]: row
        for row in cases
        if row["training_design"] == DESIGN
        and float(row["noise_std_deg"]) == NOISE
        and int(row["seed"]) == SEED
        and int(row["angle_deg"]) == RELEASE
    }
    assert set(selected) == {"direct", "savgol", "weak"}
    assert all(row["status"] == "completed" for row in selected.values())

    with np.load(RUN / "test_reference.npz") as archive:
        ref_index = int(np.flatnonzero(archive["angle_deg"] == RELEASE)[0])
        time = archive["time_s"].copy()
        reference_theta = archive["theta_rad"][ref_index].copy()
        reference_omega = archive["omega_rad_s"][ref_index].copy()
    with np.load(RUN / "test_predictions.npz") as archive:
        theta = archive["theta_rad"]
        omega = archive["omega_rad_s"]
        trajectories = {
            method: (theta[int(row["prediction_index"])].copy(), omega[int(row["prediction_index"])].copy())
            for method, row in selected.items()
        }

    plt.rcParams.update({"font.size": 11, "axes.titlesize": 12, "axes.labelsize": 11, "savefig.facecolor": "white"})
    physics_fig, schematic = plt.subplots(figsize=(5.6, 6.4), layout="constrained")

    schematic.set_xlim(-1.35, 1.55)
    schematic.set_ylim(-1.55, 1.35)
    schematic.set_aspect("equal")
    schematic.axis("off")
    schematic.set_title("Ideal pendulum at a 95° release", fontweight="bold", pad=12)
    pivot = np.array([0.0, 0.95])
    release_rad = np.deg2rad(RELEASE)
    bob = pivot + np.array([np.sin(release_rad), -np.cos(release_rad)])
    schematic.plot([0, 0], [0.95, -0.25], color="#A7B1BC", linestyle=":", linewidth=1.5)
    schematic.plot([pivot[0], bob[0]], [pivot[1], bob[1]], color=COLORS["reference"], linewidth=2.6)
    schematic.scatter([pivot[0]], [pivot[1]], s=42, color=COLORS["reference"], zorder=4)
    schematic.scatter([bob[0]], [bob[1]], s=200, color="#3D708B", zorder=4)
    arc = np.linspace(0, release_rad, 50)
    schematic.plot(0.31 * np.sin(arc), 0.95 - 0.31 * np.cos(arc), color="#5D6570", linewidth=1.4)
    schematic.text(0.29, 0.45, r"$\theta_0=95^\circ$", fontsize=12)
    schematic.annotate("", xy=(bob[0], bob[1] - 0.57), xytext=(bob[0], bob[1] - 0.1),
                       arrowprops={"arrowstyle": "->", "color": "#C45A0A", "lw": 2})
    schematic.text(bob[0] + 0.11, bob[1] - 0.32, r"$mg$", color="#C45A0A",
                   ha="left", va="center", fontsize=12)
    schematic.text(0, -0.2, r"$\ddot\theta=-\frac{g}{L}\sin\theta$", ha="center", va="top", fontsize=16)
    schematic.text(0, -0.67, r"$E_{\mathrm{phys}}=\frac{\omega^2}{2}+\frac{g}{L}(1-\cos\theta)$",
                   ha="center", va="top", fontsize=13)
    schematic.text(-1.3, -1.33, "Held-out test: 95° release\nWide training: 5°, 15°, 30°, 60°\nAngle noise: 2°; seed: 0",
                   fontsize=10, va="top", linespacing=1.45)
    PHYSICS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    physics_fig.savefig(PHYSICS_OUTPUT, dpi=180)
    plt.close(physics_fig)

    result_fig, (angle_ax, energy_ax) = plt.subplots(2, 1, figsize=(10.4, 7.2), sharex=True, layout="constrained")
    data = {"reference": (reference_theta, reference_omega), **trajectories}
    for method in ["reference", "direct", "savgol", "weak"]:
        th, om = data[method]
        color, style = COLORS[method], STYLES[method]
        angle_ax.plot(time, np.rad2deg(th), color=color, ls=style, lw=1.8 if method == "reference" else 1.5,
                      label=LABELS[method])
        e = energy(th, om)
        deviation = np.abs(e - e[0]) / e[0]
        energy_ax.plot(time, np.maximum(deviation, 1e-13), color=color, ls=style,
                       lw=1.8 if method == "reference" else 1.5)

    angle_ax.set_title("A  Predicted angle", loc="left", fontweight="bold")
    angle_ax.set_ylabel("Angle (degrees)")
    angle_ax.set_ylim(-110, 110)
    angle_ax.legend(loc="upper right", ncol=2, fontsize=9, framealpha=0.95)
    energy_ax.set_title("B  Deviation from physical energy", loc="left", fontweight="bold")
    energy_ax.set_ylabel(r"$|E(t)-E(0)|/E(0)$")
    energy_ax.set_xlabel("Time after release (seconds)")
    energy_ax.set_yscale("log")
    energy_ax.set_ylim(1e-12, 2e2)
    angle_ax.set_xlim(0, 3)
    for ax in (angle_ax, energy_ax):
        ax.grid(color="#D9E1E8", linewidth=0.75)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    result_fig.suptitle("A completed trajectory can still violate the physical energy law", fontsize=16, fontweight="bold")
    result_fig.savefig(RESULT_OUTPUT, dpi=180)
    plt.close(result_fig)


if __name__ == "__main__":
    main()
