#!/usr/bin/env python3
"""Explain archived SINDy guard stops without refitting or changing the test set."""

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from pendulum_research.noise_study import model_from_record
from pendulum_research.physics import Simulation
from pendulum_research.sindy import COEFFICIENT_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
NOISE = ROOT / "results/noise_sindy"
ENERGY = ROOT / "results/energy_drift"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, records):
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def verify_inputs():
    sources = {
        NOISE: ("config.json", "reference_config.json", "selected_models.csv", "test_metrics.csv",
                "selection_frozen.json", "summary.csv"),
        ENERGY: ("config.json", "trajectory_energy.csv"),
    }
    hashes = {}
    for folder, names in sources.items():
        assert json.loads((folder / "run_status.json").read_text())["status"] == "completed"
        manifest = {key: sha for sha, key in (line.split("  ", 1) for line in (folder / "SHA256SUMS").read_text().splitlines())}
        for name in names:
            path = folder / name
            key = path.relative_to(ROOT).as_posix()
            sha = digest(path)
            if sha != manifest[key]:
                raise ValueError(f"Archived artifact differs from its recorded hash: {key}")
            hashes[key] = sha
    frozen = json.loads((NOISE / "selection_frozen.json").read_text())
    if hashes["results/noise_sindy/selected_models.csv"] != frozen["selected_models_sha256"]:
        raise ValueError("The selected equations do not match the Phase 2 freeze record.")
    return hashes


def replay_guard(model, angle, settings, limits):
    def rhs(_time, state):
        theta, omega = state
        return omega, model.acceleration(theta, omega)

    def guard(_time, state):
        return min(limits["angle_limit_rad"] - abs(state[0]), limits["speed_limit_rad_s"] - abs(state[1]))

    guard.direction = -1
    guard.terminal = True
    solution = solve_ivp(rhs, (0.0, settings.duration_s), (math.radians(angle), 0.0),
                         method="DOP853", events=guard, rtol=settings.rtol,
                         atol=settings.atol, max_step=settings.max_step_s)
    if not solution.success or solution.status != 1 or len(solution.t_events[0]) != 1:
        raise ValueError(f"Could not reproduce the archived guard event at {angle} degrees.")
    theta, omega = (float(x) for x in solution.y_events[0][0])
    if abs(guard(0, (theta, omega))) > 1e-7:
        raise ValueError("Event state does not satisfy the guard equation.")
    hits = [label for label, value, limit in (
        ("angle", theta, limits["angle_limit_rad"]),
        ("speed", omega, limits["speed_limit_rad_s"]),
    ) if abs(abs(value) - limit) <= 1e-7]
    return {"guard": "+".join(hits), "stop_s": float(solution.t_events[0][0]),
            "stop_theta_rad": theta, "stop_omega_rad_s": omega}


def release_record(test, row, model, k):
    angle = float(test["angle_deg"])
    theta = math.radians(angle)
    reference = -k * math.sin(theta)
    fitted = model.acceleration(theta, 0.0)
    c_theta, c_cubic, c_sine, c_omega = model.coefficients
    return {
        "prediction_index": int(test["prediction_index"]), "model_id": test["model_id"],
        "seed": int(test["seed"]), "training_set": test["training_set"], "method": test["method"],
        "noise_std_deg": float(test["noise_std_deg"]), "angle_deg": angle, "coverage": test["coverage"],
        "status": test["status"], "support": row["support"], "validation_rmse_rad": float(row["validation_rmse_rad"]),
        **dict(zip(COEFFICIENT_COLUMNS, model.coefficients)),
        "reference_rest_acceleration_rad_s2": reference, "fitted_rest_acceleration_rad_s2": fitted,
        "fitted_rest_direction": "outward" if fitted > 0 else "inward" if fitted < 0 else "zero",
        "velocity_term_sign": "positive" if c_omega > 0 else "negative" if c_omega < 0 else "zero",
        "linear_taylor_coefficient": c_theta + c_sine, "cubic_taylor_coefficient": c_cubic - c_sine / 6,
        "opposing_linear_sine_scale": min(abs(c_theta), abs(c_sine)) if c_theta * c_sine < 0 else 0.0,
    }


def condition_counts(releases):
    groups = defaultdict(list)
    for row in releases:
        groups[(row["noise_std_deg"], row["training_set"], row["method"], row["angle_deg"])].append(row)
    return [
        dict(zip(("noise_std_deg", "training_set", "method", "angle_deg"), keys),
             cases=len(group), state_limits=sum(row["status"] == "state_limit" for row in group),
             completed=sum(row["status"] == "completed" for row in group),
             outward_at_release=sum(row["fitted_rest_direction"] == "outward" for row in group))
        for keys, group in sorted(groups.items())
    ]


def draw_figure(path, replays, low_validation, models, k):
    plt.rcParams.update({"font.size": 10, "axes.labelsize": 10, "axes.titlesize": 11, "legend.fontsize": 8.5})
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(9.55, 3.36), gridspec_kw={"width_ratios": [1.15, 1]})
    sample_deg = np.linspace(0, 90, 301)
    theta = np.deg2rad(sample_deg)
    model = models[low_validation["model_id"]]
    ax.axvspan(10, 20, color="#dfe6ef", alpha=.65, label="Validation angles: 10°, 20°")
    ax.plot(sample_deg, -k * np.sin(theta), color="#215788", lw=2.1, label="True pendulum")
    ax.plot(sample_deg, [model.acceleration(q, 0) for q in theta], color="#b35023", lw=2.1,
            label="Lowest validation RMSE among stops")
    ax.scatter([low_validation["angle_deg"]], [low_validation["fitted_rest_acceleration_rad_s2"]],
               color="#b35023", edgecolor="white", zorder=4, s=46)
    ax.axhline(0, color="#40434b", lw=.7)
    ax.set(title="(a) Acceleration at release", xlabel="Initial angle (deg)", ylabel="Acceleration (rad/s²)",
           xlim=(0, 94), xticks=[0, 15, 30, 45, 60, 75, 90], yscale="symlog")
    ax.margins(y=.12)
    ax.legend(loc="upper left", frameon=True, framealpha=.95)

    colors = {"direct": "#215788", "savgol": "#b35023"}
    angles = [45, 75, 90]
    x = np.arange(3)
    for method, offset, label in (("direct", -.19, "P1 central"), ("savgol", .19, "P2 Savitzky-Golay")):
        heights = [sum(row["angle_deg"] == a and row["method"] == method for row in replays) for a in angles]
        bars = bx.bar(x + offset, heights, width=.34, color=colors[method], label=label, zorder=3)
        bx.bar_label(bars, padding=2, fontsize=9)
    bx.set(title="(b) Archived guard stops", xlabel="Initial angle (deg)", ylabel="Stopped rollouts",
           xticks=x, xticklabels=angles, ylim=(0, 62))
    bx.legend(loc="upper left", frameon=True)
    for axis in (ax, bx):
        axis.set_axisbelow(True)
        axis.grid(axis="y", alpha=.23)
        axis.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(pad=1.2, w_pad=2.1)
    fig.savefig(path, dpi=220)
    plt.close(fig)


def run(output, figures):
    hashes = verify_inputs()
    noise = json.loads((NOISE / "config.json").read_text())
    config = json.loads((NOISE / "reference_config.json").read_text())
    energy = json.loads((ENERGY / "config.json").read_text())
    nominal = Simulation(**config["simulation"])
    tight = replace(nominal, **energy["tightened_rollout"])
    k = config["physics"]["gravity_m_s2"] / config["physics"]["length_m"]
    if k != energy["physical_k_s2"]:
        raise ValueError("Phase 2 and Phase 3 reference dynamics disagree.")
    records = {r["model_id"]: r for r in read_csv(NOISE / "selected_models.csv")}
    models = {key: model_from_record(row) for key, row in records.items()}
    archived = read_csv(NOISE / "test_metrics.csv")
    refined = {int(r["prediction_index"]): r for r in read_csv(ENERGY / "trajectory_energy.csv")}
    if len(archived) != len(refined) or len(archived) != len(models) * len(config["splits"]["test"]):
        raise ValueError("Expected exactly one archived test row per model and test angle.")
    releases, replays = [], []
    for test in archived:
        model_id = test["model_id"]
        index = int(test["prediction_index"])
        phase3 = refined[index]
        if (phase3["model_id"], phase3["nominal_status"], phase3["tight_status"]) != (model_id, test["status"], test["status"]):
            raise ValueError(f"Phase 2 and Phase 3 rollout records disagree at {index}.")
        if test["status"] not in {"completed", "state_limit"} or models[model_id] is None:
            raise ValueError(f"Unexpected frozen test status or missing model at {index}.")
        row = release_record(test, records[model_id], models[model_id], k)
        releases.append(row)
        if row["status"] == "state_limit":
            a = replay_guard(models[model_id], row["angle_deg"], nominal, noise["rollout"])
            b = replay_guard(models[model_id], row["angle_deg"], tight, noise["rollout"])
            replays.append({**row, **{f"nominal_{key}": val for key, val in a.items()},
                            **{f"tight_{key}": val for key, val in b.items()},
                            "stop_time_absolute_gap_s": abs(a["stop_s"] - b["stop_s"]),
                            "trigger_agreement": int(a["guard"] == b["guard"])})
    low_validation = min(replays, key=lambda r: (r["validation_rmse_rad"], r["prediction_index"]))
    max_cancellation = max(replays, key=lambda r: (r["opposing_linear_sine_scale"], -r["prediction_index"]))
    completed = [r for r in releases if r["status"] == "completed"]
    failed_models = {r["model_id"] for r in replays}
    min_val = low_validation["validation_rmse_rad"]
    same_group = [r for r in releases if all(r[field] == low_validation[field]
                  for field in ("noise_std_deg", "training_set", "method"))]
    group_model_ids = {r["model_id"] for r in same_group}
    grouped_scores = [float(records[key]["validation_rmse_rad"]) for key in group_model_ids]
    theory_p1_noise = {str(level): math.sqrt(6) * math.radians(level) / nominal.dt_s**2
                       for level in noise["noise_std_deg"] if level}
    summary = {
        "status": "completed", "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "archived_model_count": len(models), "test_rollouts": len(releases), "archived_guard_stops": len(replays),
        "models_with_guard_stop": len(failed_models),
        "stops_by_initial_angle_deg": dict(sorted(Counter(str(int(r["angle_deg"])) for r in replays).items())),
        "stops_by_method": Counter(r["method"] for r in replays),
        "stops_by_velocity_term_sign": Counter(r["velocity_term_sign"] for r in replays),
        "stops_by_rest_direction": Counter(r["fitted_rest_direction"] for r in replays),
        "completions_by_rest_direction": Counter(r["fitted_rest_direction"] for r in completed),
        "nominal_guard_type": Counter(r["nominal_guard"] for r in replays),
        "tight_guard_type": Counter(r["tight_guard"] for r in replays),
        "guard_type_agreement": sum(r["trigger_agreement"] for r in replays),
        "max_stop_time_gap_s": max(r["stop_time_absolute_gap_s"] for r in replays),
        "median_stop_time_gap_s": median(r["stop_time_absolute_gap_s"] for r in replays),
        "median_tight_stop_time_s": median(r["tight_stop_s"] for r in replays),
        "minimum_tight_stop_time_s": min(r["tight_stop_s"] for r in replays),
        "lowest_validation_rmse_stop": low_validation,
        "lowest_validation_rmse_stop_group": {
            "model_count": len(group_model_ids), "validation_rmse_median_rad": median(grouped_scores),
            "one_based_validation_rank": 1 + sum(score < min_val for score in grouped_scores),
            "model_count_with_stop": len(group_model_ids & failed_models),
        },
        "largest_opposing_coefficient_stop": max_cancellation,
        "central_acceleration_noise_sd_rad_s2": theory_p1_noise,
        "limits": noise["rollout"],
        "input_sha256": hashes,
        "script_sha256": digest(Path(__file__)),
    }
    write_csv(output / "release_diagnostics.csv", releases)
    write_csv(output / "guard_replays.csv", replays)
    write_csv(output / "failure_by_condition.csv", condition_counts(releases))
    draw_figure(figures / "failure_mechanisms.png", replays, low_validation, models, k)
    write_json(output / "failure_summary.json", summary)
    manifest = sorted([*output.iterdir(), *figures.iterdir()])
    (output / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.relative_to(ROOT)}\n" for p in manifest))
    print(json.dumps({key: val for key, val in summary.items() if key not in ("input_sha256", "script_sha256")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/failure_diagnostics")
    parser.add_argument("--figures", type=Path, default=ROOT / "figures/failure_diagnostics")
    args = parser.parse_args()
    output, figures = args.output.resolve(), args.figures.resolve()
    if (not output.is_relative_to(ROOT) or not figures.is_relative_to(ROOT) or output.exists() or figures.exists()
            or output.is_relative_to(figures) or figures.is_relative_to(output)):
        parser.error("Use two fresh and separate directories within the project.")
    output.mkdir(parents=True)
    figures.mkdir(parents=True)
    try:
        run(output, figures)
    except Exception as error:
        write_json(output / "run_status.json", {"status": "failed", "error": str(error)})
        raise
    write_json(output / "run_status.json", {"status": "completed"})


if __name__ == "__main__":
    main()
