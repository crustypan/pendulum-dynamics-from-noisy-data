#!/usr/bin/env python3
"""Audit the frozen evidence and page counts in the Phase 4 release."""

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/report-packages"))

from pypdf import PdfReader


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def saved_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def rows(relative):
    with (ROOT / relative).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def verify_hashes(expected):
    for relative, sha in expected.items():
        path = (ROOT / relative).resolve()
        assert path.is_relative_to(ROOT) and digest(path) == sha, relative


def audit():
    checked = {}
    for run in ("baseline", "noise_sindy", "energy_drift", "failure_diagnostics"):
        folder = Path("results") / run
        manifest = (ROOT / folder / "SHA256SUMS").read_text().splitlines()
        checksums = {path: sha for sha, path in (line.split("  ", 1) for line in manifest)}
        verify_hashes(checksums)
        assert saved_json(folder / "run_status.json")["status"] == "completed"
        if run != "failure_diagnostics":
            verify_hashes(saved_json(folder / "run_metadata.json")["source_sha256"])
        checked[run] = len(checksums)

    lean = saved_json("results/lean_verification/verification.json")
    frozen_hash = digest(ROOT / "results/noise_sindy/selected_models.csv")
    assert lean["status"] == "verified" and lean["theorem_count"] == 13
    assert lean["frozen_coefficients_sha256"] == frozen_hash
    assert saved_json("results/noise_sindy/selection_frozen.json")["selected_models_sha256"] == frozen_hash
    verify_hashes(lean["source_sha256"])

    diag = saved_json("results/failure_diagnostics/failure_summary.json")
    verify_hashes(diag["input_sha256"])
    assert diag["script_sha256"] == digest(ROOT / "scripts/run_failure_diagnostics.py")
    frozen = {r["model_id"]: r for r in rows("results/noise_sindy/selected_models.csv")}
    assert len(frozen) == diag["archived_model_count"] == 244
    originals = rows("results/noise_sindy/test_metrics.csv")
    releases = rows("results/failure_diagnostics/release_diagnostics.csv")
    assert len(releases) == len(originals) == diag["test_rollouts"] == 732
    for x, y in zip(releases, originals):
        for field in ("prediction_index", "model_id", "status", "training_set", "method"):
            assert x[field] == y[field], (field, x["prediction_index"])
        assert float(x["angle_deg"]) == float(y["angle_deg"])
        for col in ("c_theta", "c_theta_cubed", "c_sin_theta", "c_omega"):
            assert float(x[col]) == float(frozen[x["model_id"]][col]), (x["model_id"], col)
        theta = math.radians(float(x["angle_deg"]))
        c1, c2, c3 = (float(x[name]) for name in ("c_theta", "c_theta_cubed", "c_sin_theta"))
        assert math.isclose(c1 * theta + c2 * theta**3 + c3 * math.sin(theta),
                            float(x["fitted_rest_acceleration_rad_s2"]), abs_tol=1e-12)
        assert math.isclose(-9.81 * math.sin(theta), float(x["reference_rest_acceleration_rad_s2"]),
                            abs_tol=1e-12)
    stops = rows("results/failure_diagnostics/guard_replays.csv")
    guard_indices = {row["prediction_index"] for row in originals if row["status"] == "state_limit"}
    assert len(guard_indices) == len(stops) == diag["archived_guard_stops"] == 98
    assert {row["prediction_index"] for row in stops} == guard_indices
    counts = Counter()
    for row in stops:
        for solver in ("nominal", "tight"):
            assert row[f"{solver}_guard"] == "speed"
            assert abs(abs(float(row[f"{solver}_stop_omega_rad_s"])) - 100) <= 1e-7
            assert abs(float(row[f"{solver}_stop_theta_rad"])) < 2 * math.pi
            assert 0 < float(row[f"{solver}_stop_s"]) <= 10
        counts[str(int(float(row["angle_deg"])))] += 1
    assert counts == diag["stops_by_initial_angle_deg"]
    assert sum(int(row["trigger_agreement"]) for row in stops) == diag["guard_type_agreement"] == 98

    receipt = saved_json("report/pdf/build_receipt.json")
    assert receipt["status"] == "built"
    verify_hashes(receipt["input_sha256"])
    counts_pdf = {"research_report.pdf": 6, "research_highlight.pdf": 1}
    assert set(counts_pdf) == set(receipt["outputs"])
    for file, count in counts_pdf.items():
        path = ROOT / "report/pdf" / file
        info = receipt["outputs"][file]
        assert info["sha256"] == digest(path) and info["pages"] == len(PdfReader(path).pages) == count

    docs = ("README.md", "report/README.md", "report/research_report.md",
            "report/research_highlight.md", "docs/phase4_failure_analysis.md",
            "docs/experiment_log.md", "docs/research_decisions.md")
    link_count = 0
    for name in docs:
        file = ROOT / name
        for target in re.findall(r"\]\(([^) ]+)\)", file.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "#")):
                continue
            path = (file.parent / target.split("#", 1)[0]).resolve()
            assert path.is_relative_to(ROOT) and path.exists(), (name, target)
            link_count += 1

    paths = subprocess.run(["git", "--no-optional-locks", "ls-files", "-z", "--cached",
                            "--others", "--exclude-standard"], cwd=ROOT, check=True,
                           capture_output=True).stdout.decode().split("\0")
    paths = [path for path in paths if path]
    assert not any(path.startswith((".tools/", ".venv/", ".cache/", ".tmp/", ".local/", "lean/.lake/"))
                   for path in paths)
    largest = max(paths, key=lambda path: (ROOT / path).stat().st_size)
    assert (ROOT / largest).stat().st_size < 100 * 1024**2
    return {"status": "verified", "artifact_checksums": checked, "lean_theorems": lean["theorem_count"],
            "frozen_model_sha256": frozen_hash, "test_release_records": len(releases),
            "speed_guard_replays_checked": len(stops), "pdf_pages": counts_pdf,
            "relative_links_checked": link_count, "largest_versionable_file": largest,
            "largest_versionable_file_bytes": (ROOT / largest).stat().st_size}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
