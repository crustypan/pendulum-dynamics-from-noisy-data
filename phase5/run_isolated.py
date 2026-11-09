#!/usr/bin/env python3
"""Use the v1 environment with a read-only project mount and Phase 5 writes."""

import argparse
import os
from pathlib import Path
import resource
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("A command is required after --.")

    phase = Path(__file__).resolve().parent
    root = phase.parent
    for relative in (".tmp", ".cache/matplotlib", ".cache/home"):
        (phase / relative).mkdir(parents=True, exist_ok=True, mode=0o700)

    environment = {
        "PATH": f"{root}/.venv/bin:/usr/bin:/bin",
        "HOME": str(phase / ".cache/home"),
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "PYTHONPATH": str(root / "src"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(phase / ".tmp"),
        "XDG_CACHE_HOME": str(phase / ".cache"),
        "MPLCONFIGDIR": str(phase / ".cache/matplotlib"),
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }
    sandbox = [
        "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--ro-bind", "/etc/fonts", "/etc/fonts", "--ro-bind", "/etc/passwd", "/etc/passwd",
        "--proc", "/proc", "--dev", "/dev",
        "--ro-bind", str(root), str(root),
        "--bind", str(phase), str(phase),
        "--bind", str(phase / ".tmp"), "/tmp",
        "--chdir", str(root), "--clearenv",
    ]
    for name, value in environment.items():
        sandbox.extend(("--setenv", name, value))
    sandbox.extend(("--remount-ro", "/", "--", *command))

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 2**20, 256 * 2**20))
    os.nice(10)
    scope = [
        "/usr/bin/systemd-run", "--user", "--scope", "--quiet",
        "--unit", f"physics-lean4-phase5-{os.getpid()}-{time.time_ns()}",
        "--property=CPUQuota=50%", "--property=CPUWeight=1",
        "--property=MemoryMax=1G", "--property=MemorySwapMax=0",
        "--property=TasksMax=32", *sandbox,
    ]
    os.execv(scope[0], scope)


if __name__ == "__main__":
    main()
