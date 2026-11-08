#!/usr/bin/env python3
"""Run the project-local Lean toolchain in the existing filesystem sandbox."""

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = ROOT / ".tools/lean-4.24.0-linux"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", action="store_true", help="Enable network access for setup.")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("A command is required.")
    if command[0] in ("lake", "lean"):
        executable = TOOLCHAIN / "bin" / command[0]
        if not executable.is_file():
            parser.error("Install the project toolchain with scripts/install_lean.py first.")
        if command[0] == "lake" and command[1:] != ["--version"]:
            command = [str(executable), "--dir", str(ROOT / "lean"), *command[1:]]
        else:
            command = [str(executable), *command[1:]]
    environment = {
        "PATH": f"{TOOLCHAIN}/bin:{ROOT}/.venv/bin:/usr/bin:/bin",
        "LEAN_NUM_THREADS": "1",
        "RAYON_NUM_THREADS": "1",
        "MATHLIB_CACHE_DIR": str(ROOT / ".cache/mathlib"),
        "MATHLIB_NO_CACHE_ON_UPDATE": "1",
        "ELAN_HOME": str(ROOT / ".tools/elan"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "pack.threads",
        "GIT_CONFIG_VALUE_0": "1",
    }
    runner = ["/usr/bin/python3", "-B", str(ROOT / "scripts/run_isolated.py")]
    if args.network:
        runner.append("--network")
    os.chdir(ROOT)
    os.execv(runner[0], [*runner, "--", "/usr/bin/env",
                        *(f"{name}={value}" for name, value in environment.items()), *command])


if __name__ == "__main__":
    main()
