"""Fit M1-M3 using sampled angles alone, without physical reference parameters."""

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class Model:
    name: str
    a: float
    b: float = 0.0

    def __post_init__(self):
        if self.name not in ("M1", "M2", "M3") or not np.isfinite([self.a, self.b]).all():
            raise ValueError("A baseline model needs a known name and finite coefficients.")
        if self.name != "M3" and self.b != 0:
            raise ValueError("Only the cubic model has a cubic coefficient.")

    def acceleration(self, theta):
        if self.name == "M2":
            return -self.a * np.sin(theta)
        return -self.a * theta - self.b * theta**3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict):
        saved = dict(value)
        equation = saved.pop("equation", None)
        model = cls(**saved)
        if equation is not None and equation != model.equation:
            raise ValueError("The saved equation disagrees with the model coefficients.")
        return model

    @property
    def equation(self) -> str:
        if self.name == "M2":
            return f"theta_ddot = -({self.a:.12g}) * sin(theta)"
        if self.name == "M3":
            return f"theta_ddot = -({self.a:.12g}) * theta - ({self.b:.12g}) * theta^3"
        return f"theta_ddot = -({self.a:.12g}) * theta"


def angle_derivatives(theta, dt_s: float):
    """Estimate acceleration separately within each trajectory and discard its endpoints."""
    theta = np.asarray(theta, dtype=float)
    if theta.ndim != 1 or theta.size < 5 or not np.isfinite(theta).all() or not np.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("A finite one-dimensional trajectory and a positive interval are required.")
    acceleration = (
        -theta[4:] + 16 * theta[3:-1] - 30 * theta[2:-2]
        + 16 * theta[1:-3] - theta[:-4]
    ) / (12 * dt_s**2)
    return theta[2:-2], acceleration


def fit_models(training_angles: Iterable[np.ndarray], dt_s: float) -> dict[str, Model]:
    """All fitted coefficients come from angle observations and their sampling interval."""
    samples = [angle_derivatives(theta, dt_s) for theta in training_angles]
    if not samples:
        raise ValueError("At least one training trajectory is required.")
    theta = np.concatenate([sample[0] for sample in samples])
    target = np.concatenate([sample[1] for sample in samples])
    designs = {
        "M1": -theta[:, None],
        "M2": -np.sin(theta)[:, None],
        "M3": -np.column_stack((theta, theta**3)),
    }
    models = {}
    for name, design in designs.items():
        coefficients, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
        if rank != design.shape[1]:
            raise ValueError(f"The {name} training design is rank deficient.")
        models[name] = Model(name, float(coefficients[0]), float(coefficients[1]) if name == "M3" else 0.0)
    return models
