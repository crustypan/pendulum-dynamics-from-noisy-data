"""Seed-level summaries and figures from the saved Phase 2 experiment."""

import csv
from collections import Counter, defaultdict
import math
from pathlib import Path
from statistics import mean, stdev

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from pendulum_research.sindy import TERMS

GROUP_FIELDS = ("noise_std_deg", "training_set", "method")
DERIVATIVE_FIELDS = ("angle_rmse_rad", "velocity_rmse_rad_s", "acceleration_rmse_rad_s2")


def grouped(rows: list[dict], fields: tuple[str, ...]) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in fields)].append(row)
    return groups


def stats(values, name: str) -> dict:
    finite = [float(value) for value in values if value is not None and value != ""]
    return {
        f"{name}_n": len(finite),
        f"{name}_mean": mean(finite) if finite else None,
        f"{name}_sd": stdev(finite) if len(finite) >= 2 else None,
    }


def wilson(successes: int, count: int) -> tuple[float | None, float | None]:
    if count < 2:
        return None, None
    z = 1.959963984540054
    proportion = successes / count
    denominator = 1 + z**2 / count
    center = (proportion + z**2 / (2 * count)) / denominator
    half_width = z * math.sqrt(proportion * (1 - proportion) / count + z**2 / (4 * count**2)) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def summarize(models: list[dict], tests: list[dict], derivatives: list[dict]) -> tuple[list, list, list]:
    summaries, supports, by_angle = [], [], []
    derivative_by_model = grouped([row for row in derivatives if row["status"] == "selected"], ("model_id",))
    for keys, rows in grouped(models, GROUP_FIELDS).items():
        group = dict(zip(GROUP_FIELDS, keys))
        total = len(rows)
        exact = sum(row["exact_sine_support"] for row in rows)
        ci_low, ci_high = wilson(exact, total)
        complete = sum(row["all_test_angles_completed"] for row in rows)
        counts = Counter(row["support"] for row in rows)
        item = {
            **group,
            "repetitions": total,
            "selected_models": total - counts["no_selected_model"],
            "exact_support_count": exact,
            "exact_support_rate": exact / total,
            "exact_support_ci_low": ci_low, "exact_support_ci_high": ci_high,
            "all_test_angles_completed_count": complete,
            "all_test_angles_completed_rate": complete / total,
        }
        for field in (
            "term_count", "train_acceleration_rmse_rad_s2", "validation_rmse_rad", "test_rmse_rad",
            "sine_coefficient_relative_error", "exact_sine_coefficient_relative_error",
            "corr_theta_cubic", "corr_theta_sine", "corr_cubic_sine", "scaled_condition_number",
        ):
            item.update(stats((row[field] for row in rows), field))
        for field in DERIVATIVE_FIELDS:
            # Each seed contributes one mean over its two validation angles.
            seed_means = [
                mean(row[field] for row in derivative_by_model[(model["model_id"],)])
                for model in rows if (model["model_id"],) in derivative_by_model
            ]
            item.update(stats(seed_means, f"derivative_{field}"))
        for term in TERMS:
            item[f"{term}_selected_count"] = sum(count for name, count in counts.items() if term in name.split("+"))
        summaries.append(item)
        for name, count in sorted(counts.items()):
            supports.append({**group, "support": name, "count": count, "fraction": count / total})

    for keys, rows in grouped(tests, (*GROUP_FIELDS, "angle_deg", "coverage")).items():
        completed = sum(row["status"] == "completed" for row in rows)
        by_angle.append({
            **dict(zip((*GROUP_FIELDS, "angle_deg", "coverage"), keys)),
            "repetitions": len(rows), "completed": completed,
            "state_limit_failures": sum(row["status"] == "state_limit" for row in rows),
            "numerical_failures": sum(row["status"] == "numerical_failure" for row in rows),
            "no_selected_model": sum(row["status"] == "no_selected_model" for row in rows),
            **stats((row["theta_rmse_rad"] for row in rows), "theta_rmse_rad"),
            **stats((row["period_relative_error"] for row in rows), "period_relative_error"),
        })
    return summaries, supports, by_angle


def paired_errors(models: list[dict]) -> list[dict]:
    """Compare mean test errors within the same seed when both sides complete."""
    comparisons = []
    for (noise,), rows in grouped(models, ("noise_std_deg",)).items():
        lookup = {(row["seed"], row["training_set"], row["method"]): row["test_rmse_rad"] for row in rows}
        seeds = sorted({row["seed"] for row in rows})
        contrasts = [
            ("savgol_minus_direct", training, (training, "direct"), (training, "savgol"))
            for training in ("training_A", "training_B")
        ] + [
            ("training_B_minus_A", method, ("training_A", method), ("training_B", method))
            for method in ("direct", "savgol")
        ]
        for comparison, condition, lower, upper in contrasts:
            differences = [
                lookup[(seed, *upper)] - lookup[(seed, *lower)] for seed in seeds
                if lookup[(seed, *upper)] is not None and lookup[(seed, *lower)] is not None
            ]
            comparisons.append({
                "noise_std_deg": noise, "comparison": comparison, "condition": condition,
                "intended_pairs": len(seeds), **stats(differences, "rmse_difference_rad"),
            })
    return comparisons


def write_rows(path: Path, rows: list[dict]):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_phase2(summary_csv: Path, figures: Path):
    with summary_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    series = grouped(rows, ("training_set", "method"))
    styles = {
        "training_A": {"color": "#2166ac", "marker": "o"},
        "training_B": {"color": "#af4d20", "marker": "s"},
    }
    labels = {"direct": "P1 central", "savgol": "P2 Savitzky–Golay"}
    plots = [
        ("test_rmse_rad_mean", "Test angle RMSE (rad)", "log"),
        ("exact_support_rate", "Exact sine-only recovery", "linear"),
        ("sine_coefficient_relative_error_mean", "Relative sine coefficient error", "log"),
        ("all_test_angles_completed_rate", "Fraction completing all test angles", "linear"),
    ]
    figure, axes = plt.subplots(2, 2, figsize=(10.5, 7.6))
    for (training, method), values in series.items():
        values.sort(key=lambda row: float(row["noise_std_deg"]))
        x = [float(row["noise_std_deg"]) for row in values]
        label = f"{training.replace('_', ' ').title()}, {labels[method]}"
        style = dict(styles[training], linestyle="--" if method == "direct" else "-")
        for axis, (field, title, scale) in zip(axes.flat, plots):
            y = np.array([float(row[field]) if row[field] else np.nan for row in values])
            if scale == "log":
                y[y <= 0] = np.nan
            axis.plot(x, y, label=label, **style)
            if field == "exact_support_rate":
                observed = [index for index, row in enumerate(values) if row["exact_support_ci_low"]]
                if observed:
                    low = [max(0, y[index] - float(values[index]["exact_support_ci_low"])) for index in observed]
                    high = [max(0, float(values[index]["exact_support_ci_high"]) - y[index]) for index in observed]
                    axis.errorbar(np.array(x)[observed], y[observed], yerr=[low, high],
                                  fmt="none", color=style["color"], capsize=2, alpha=0.45)
            axis.set_yscale(scale)
            axis.set_title(title)
            axis.set_xticks(x)
            axis.set_xlabel("Angle noise SD (deg)")
            axis.grid(alpha=0.22)
            if field in ("exact_support_rate", "all_test_angles_completed_rate"):
                axis.set_ylim(-0.04, 1.04)
    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    figure.suptitle("SINDy robustness to angle measurement noise", y=0.985)
    figure.legend(handles, legend_labels, loc="upper center", bbox_to_anchor=(0.5, 0.948),
                  ncol=2, frameon=False)
    figure.tight_layout(rect=(0, 0.01, 1, 0.86))
    figure.savefig(figures / "noise_robustness.png", dpi=180)
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(9, 4.1))
    for method, color in (("direct", "#b35806"), ("savgol", "#1b7837")):
        values = series[("training_B", method)]
        x = [float(row["noise_std_deg"]) for row in values]
        for axis, field, label in zip(axes, DERIVATIVE_FIELDS[1:], ("Velocity (rad/s)", "Acceleration (rad/s²)")):
            y = [float(row[f"derivative_{field}_mean"]) if row[f"derivative_{field}_mean"] else np.nan for row in values]
            axis.plot(x, y, label=labels[method], color=color, marker="o")
            axis.set_yscale("log")
            axis.set_xticks(x)
            axis.set_xlabel("Angle noise SD (deg)")
            axis.set_ylabel(f"{label} RMSE")
            axis.grid(alpha=0.22)
    axes[0].legend(frameon=False)
    figure.suptitle("Validation derivative accuracy with Training B")
    figure.tight_layout()
    figure.savefig(figures / "derivative_estimation.png", dpi=180)
    plt.close(figure)
