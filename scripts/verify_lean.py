#!/usr/bin/env python3
"""Build the Lean project offline and record the theorem dependencies."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LEAN = ROOT / "lean"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded(command: list[str], path: Path) -> str:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(f"$ {shlex.join(command)}\n{result.stdout}{result.stderr}\nexit_code={result.returncode}\n")
    if result.returncode:
        raise RuntimeError(f"Verification command failed. See {path.name}.\n{result.stderr}{result.stdout}")
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/lean_verification")
    output = parser.parse_args().output.resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        parser.error("Use a new output directory within this project.")
    output.mkdir(parents=True)

    sources = sorted([*LEAN.glob("*.lean"), *LEAN.glob("Pendulum/*.lean")])
    for source in sources:
        if re.search(r"\b(sorry|admit|axiom|native_decide)\b", source.read_text()):
            raise ValueError(f"Unexpected placeholder or trust extension in {source.name}.")
    runner = ["python3", "-B", "scripts/run_lean.py", "--"]
    recorded(["python3", "-B", "scripts/generate_frozen_lean.py", "--check"], output / "frozen_export.log")
    lean_version = recorded([*runner, "lean", "--version"], output / "lean_version.log")
    lake_version = recorded([*runner, "lake", "--version"], output / "lake_version.log")
    recorded([*runner, "lake", "build"], output / "build.log")
    audit = recorded([*runner, "lake", "env", "lean", "-DwarningAsError=true", str(LEAN / "Audit.lean")],
                     output / "axioms.log")

    expected = re.findall(r"^#print axioms ([\w.]+)$", (LEAN / "Audit.lean").read_text(), flags=re.MULTILINE)
    audited = {}
    for name, dependencies in re.findall(r"'([^']+)' depends on axioms:\s*\[([^\]]*)\]", audit):
        audited[name] = sorted(word.strip() for word in dependencies.split(",") if word.strip())
    for name in re.findall(r"'([^']+)' does not depend on any axioms", audit):
        audited[name] = []
    if set(audited) != set(expected):
        raise RuntimeError("The compiler output did not audit every listed theorem.")
    for name, dependencies in audited.items():
        if not set(dependencies) <= ALLOWED_AXIOMS:
            raise RuntimeError(f"Unexpected axioms in {name}: {dependencies}")

    manifest = json.loads((LEAN / "lake-manifest.json").read_text())
    package_pins = {}
    for package in manifest["packages"]:
        path = LEAN / ".lake/packages" / package["name"]
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True)
        if head.stdout.strip() != package["rev"]:
            raise ValueError(f"Wrong checkout revision for {package['name']}.")
        package_pins[package["name"]] = {"revision": package["rev"], "url": package["url"]}
    receipt = json.loads((ROOT / ".tools/lean-release.json").read_text())
    result = {
        "status": "verified", "lean": lean_version, "lake": lake_version,
        "mathlib_revision": package_pins["mathlib"]["revision"], "packages": package_pins,
        "lean_release_asset": receipt, "theorem_count": len(audited), "theorem_axioms": audited,
        "source_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in [*sources, LEAN / "lakefile.toml", LEAN / "lean-toolchain", LEAN / "lake-manifest.json"]
        },
        "frozen_coefficients_sha256": digest(ROOT / "results/noise_sindy/selected_models.csv"),
    }
    (output / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "theorems": result["theorem_count"],
                      "lean": lean_version, "mathlib_revision": result["mathlib_revision"]}, indent=2))


if __name__ == "__main__":
    main()
