"""Configuration validation and reference datasets with trajectory-level splits."""

import json
from pathlib import Path

import numpy as np

from pendulum_research.physics import Simulation, reference_trajectory


def load_config(path: str | Path) -> dict:
    config = json.loads(Path(path).read_text())
    splits = config["splits"]
    expected = {"training_A", "training_B", "validation", "test"}
    if set(splits) != expected:
        raise ValueError("The four named trajectory splits are required.")
    for name, angles in splits.items():
        if not angles or len(set(angles)) != len(angles):
            raise ValueError(f"The {name} split must contain distinct angles.")
        if any(not np.isfinite(angle) or not 0 < angle < 180 for angle in angles):
            raise ValueError("Initial angles must be between zero and 180 degrees.")
    if set(splits["validation"]) & set(splits["test"]):
        raise ValueError("Validation and test trajectories overlap.")
    for name in ("training_A", "training_B"):
        if set(splits[name]) & (set(splits["validation"]) | set(splits["test"])):
            raise ValueError(f"The {name} split overlaps validation or test.")
    physics = config["physics"]
    if not np.isfinite([physics["gravity_m_s2"], physics["length_m"]]).all():
        raise ValueError("Physical parameters must be finite.")
    if min(physics["gravity_m_s2"], physics["length_m"]) <= 0:
        raise ValueError("Gravity and length must be positive.")
    if physics["initial_omega_rad_s"] != 0:
        raise ValueError("This baseline protocol uses zero initial angular velocity.")
    if config["fitting"] != {
        "derivative_stencil": "five_point_central", "endpoint_samples_discarded": 2
    }:
        raise ValueError("Unsupported baseline derivative configuration.")
    if config["protocol"]["noise_std_deg"] != 0.0:
        raise ValueError("Phase 1 uses noiseless observations.")
    Simulation(**config["simulation"]).time_grid()
    return config


def generate_references(config: dict) -> dict:
    k = config["physics"]["gravity_m_s2"] / config["physics"]["length_m"]
    settings = Simulation(**config["simulation"])
    angles = sorted({angle for split in config["splits"].values() for angle in split})
    return {angle: reference_trajectory(angle, k, settings) for angle in angles}
