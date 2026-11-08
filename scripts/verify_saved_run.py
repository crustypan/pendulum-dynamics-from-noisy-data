"""Check saved Phase 1 artifacts without fitting or selecting a new model."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from pendulum_research.models import Model

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--results", type=Path, default=root / "results/baseline")
args = parser.parse_args()
output = args.results.resolve()
if not output.is_relative_to(root):
    parser.error("Saved results must belong to this project.")
status = json.loads((output / "run_status.json").read_text())
assert status == {"status": "completed", "phase": 1}
config = json.loads((output / "config.json").read_text())
k = config["physics"]["gravity_m_s2"] / config["physics"]["length_m"]
sample_count = round(config["simulation"]["duration_s"] / config["simulation"]["dt_s"]) + 1
metadata = json.loads((output / "run_metadata.json").read_text())
assert hashlib.sha256((output / "config.json").read_bytes()).hexdigest() == metadata["config_sha256"]
for relative, expected in metadata["source_sha256"].items():
    assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, relative

saved_models = json.loads((output / "models.json").read_text())
loaded_models = {
    training: {name: Model.from_dict(value) for name, value in models.items()}
    for training, models in saved_models.items()
}
with (output / "reference.csv").open(newline="") as stream:
    reference_rows = list(csv.DictReader(stream))
with (output / "predictions.csv").open(newline="") as stream:
    prediction_rows = list(csv.DictReader(stream))
with (output / "metrics.csv").open(newline="") as stream:
    metric_rows = list(csv.DictReader(stream))

references = {}
for row in reference_rows:
    references.setdefault(float(row["angle_deg"]), []).append(row)
predictions = {}
for row in prediction_rows:
    key = (row["training_set"], row["model"], row["split"], float(row["angle_deg"]))
    predictions.setdefault(key, []).append(row)
assert len(predictions) == len(metric_rows)
for metric in metric_rows:
    angle = float(metric["angle_deg"])
    key = (metric["training_set"], metric["model"], metric["split"], angle)
    predicted, reference = predictions[key], references[angle]
    assert len(predicted) == len(reference) == sample_count
    predicted_time = np.array([float(row["time_s"]) for row in predicted])
    reference_time = np.array([float(row["time_s"]) for row in reference])
    np.testing.assert_array_equal(predicted_time, reference_time)
    predicted_theta = np.array([float(row["theta_rad"]) for row in predicted])
    reference_theta = np.array([float(row["theta_rad"]) for row in reference])
    recalculated_rmse = float(np.sqrt(np.mean((predicted_theta - reference_theta)**2)))
    np.testing.assert_allclose(recalculated_rmse, float(metric["theta_rmse_rad"]), rtol=1e-13, atol=1e-15)
    np.testing.assert_allclose(predicted_theta[0], np.deg2rad(angle), rtol=0, atol=1e-14)
    assert float(predicted[0]["omega_rad_s"]) == 0
    model = loaded_models[metric["training_set"]][metric["model"]]
    expected_parameter_error = abs(model.a - k) / k
    if metric["model"] == "M2":
        np.testing.assert_allclose(float(metric["parameter_relative_error"]), expected_parameter_error, rtol=1e-13)
    else:
        assert metric["parameter_relative_error"] == ""

summary = {}
for training, models in loaded_models.items():
    summary[training] = {}
    for name, model in models.items():
        test = [row for row in metric_rows if row["training_set"] == training
                and row["model"] == name and row["split"] == "test"]
        summary[training][name] = {
            "a": model.a, "b": model.b if name == "M3" else None,
            "mean_test_rmse_rad": float(np.mean([float(row["theta_rmse_rad"]) for row in test])),
            "test_rmse_by_angle_rad": {row["angle_deg"]: float(row["theta_rmse_rad"]) for row in test},
            "mean_test_period_relative_error": float(np.mean([float(row["period_relative_error"]) for row in test])),
        }
print(json.dumps({
    "saved_run_verification": "passed",
    "reloaded_models": sum(len(models) for models in loaded_models.values()),
    "reference_trajectories": len(references),
    "verified_metric_rows": len(metric_rows),
    "verified_source_hashes": len(metadata["source_sha256"]),
    "summary": summary,
}, indent=2, allow_nan=False))
