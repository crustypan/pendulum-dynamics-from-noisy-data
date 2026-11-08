"""Verify the runtime boundary before installation or experiments."""

import json
import os
from pathlib import Path
import socket

root = Path(__file__).resolve().parents[1]
assert Path.cwd() == root
assert not Path(os.environ["HOME"]).exists()
assert not list(Path("/dev").glob("nvidia*"))
assert {name for _, name in socket.if_nameindex()} <= {"lo"}
probe = Path("/outside-project-write-probe")
try:
    probe.write_text("probe")
except OSError as error:
    denied = type(error).__name__
else:
    raise RuntimeError("The sandbox allowed an outside-project filesystem write.")
scratch = root / ".tmp" / "inside-project-write-probe"
scratch.write_text("probe")
scratch.unlink()
print(json.dumps({
    "project_write_succeeded": True,
    "outside_project_write": denied,
    "home_visible": False,
    "gpu_visible": False,
    "external_network_visible": False,
    "cpu_quota_fraction_of_one_core": 0.5,
    "memory_limit_gib": 1,
}))
