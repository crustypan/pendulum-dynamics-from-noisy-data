#!/usr/bin/env python3
"""Run a command with project-only writable storage and low-priority resource limits."""

import argparse
import os
from pathlib import Path
import resource
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", action="store_true", help="Enable networking for dependency installation.")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("A command is required.")
    root = Path(__file__).resolve().parents[1]
    if root.is_symlink():
        raise RuntimeError("The project root must be a real directory.")
    for relative in (".tmp", ".cache/pip", ".cache/matplotlib", ".config", ".local/share"):
        (root / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
    environment = {
        "PATH": f"{root}/.venv/bin:/usr/bin:/bin",
        "HOME": os.environ["HOME"],
        "USER": os.environ.get("USER", ""),
        "LOGNAME": os.environ.get("LOGNAME", ""),
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "XDG_CACHE_HOME": str(root / ".cache"),
        "XDG_CONFIG_HOME": str(root / ".config"),
        "XDG_DATA_HOME": str(root / ".local/share"),
        "TMPDIR": str(root / ".tmp"),
        "PIP_CACHE_DIR": str(root / ".cache/pip"),
        "PIP_CONFIG_FILE": "/dev/null",
        "MPLCONFIGDIR": str(root / ".cache/matplotlib"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "CUDA_VISIBLE_DEVICES": "",
    }
    bubblewrap = [
        "/usr/bin/bwrap", "--unshare-all", "--die-with-parent", "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--ro-bind", "/etc/fonts", "/etc/fonts",
        "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind", "/etc/hosts", "/etc/hosts",
        "--ro-bind", "/etc/passwd", "/etc/passwd",
        "--proc", "/proc", "--dev", "/dev",
        "--bind", str(root), str(root),
        "--bind", str(root / ".tmp"), "/tmp",
        "--chdir", str(root), "--clearenv",
    ]
    if args.network:
        bubblewrap.append("--share-net")
    for name, value in environment.items():
        bubblewrap.extend(("--setenv", name, value))
    bubblewrap.extend(("--remount-ro", "/", "--", *command))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 2**20, 256 * 2**20))
    os.nice(10)
    scope = [
        "/usr/bin/systemd-run", "--user", "--scope", "--quiet",
        "--unit", f"physics-lean4-{os.getpid()}-{time.time_ns()}",
        "--property=CPUQuota=50%", "--property=CPUWeight=1",
        "--property=MemoryMax=1G", "--property=MemorySwapMax=0",
        "--property=TasksMax=32",
        *bubblewrap,
    ]
    os.execv(scope[0], scope)


if __name__ == "__main__":
    main()
