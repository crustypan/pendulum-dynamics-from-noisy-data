"""Install the pinned official Lean release and prepare the locked Lake packages."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
NAME = "lean-4.24.0-linux"
URL = f"https://github.com/leanprover/lean4/releases/download/v4.24.0/{NAME}.tar.zst"
ARCHIVE_SIZE = 459625674
ARCHIVE_SHA256 = "b14f5e5159219dd1a1956c3b806813319f5e94ccd5bdfd56f54520609a5bb5ec"
MATHLIB_URL = "https://github.com/leanprover-community/mathlib4.git"
MATHLIB_REVISION = "f897ebcf72cd16f89ab4577d0c826cd14afaafc7"
TOOLCHAIN = ROOT / ".tools" / NAME


def command(*args, cwd: Path = ROOT, capture: bool = False) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def download_verified_chunks(staging: Path) -> list[Path]:
    """Keep each staged download file below the sandbox file-size limit."""
    chunk_size = 128 * 2**20
    checksum = hashlib.sha256()
    paths = []
    with subprocess.Popen(
        ["/usr/bin/curl", "--fail", "--silent", "--show-error", "--location",
         "--connect-timeout", "25", "--max-time", "900", "--proto", "=https", "--proto-redir", "=https", URL],
        stdout=subprocess.PIPE,
    ) as download:
        for start in range(0, ARCHIVE_SIZE, chunk_size):
            remaining = min(chunk_size, ARCHIVE_SIZE - start)
            path = staging / f"archive-{start:010d}"
            with path.open("xb") as stream:
                while remaining:
                    data = download.stdout.read(min(2**20, remaining))
                    if not data:
                        raise RuntimeError("Lean release transfer ended early.")
                    stream.write(data)
                    checksum.update(data)
                    remaining -= len(data)
            paths.append(path)
        if download.stdout.read(1) or download.wait() != 0:
            raise RuntimeError("Lean release transfer did not match the official asset.")
    if checksum.hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("Lean release SHA-256 mismatch.")
    return paths


def install_toolchain():
    receipt = ROOT / ".tools/lean-release.json"
    if TOOLCHAIN.is_dir():
        record = json.loads(receipt.read_text())
        if record["sha256"] != ARCHIVE_SHA256:
            raise RuntimeError("The existing local toolchain receipt does not match the pinned release.")
        return
    TOOLCHAIN.parent.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="lean-release-", dir=ROOT / ".tmp") as work:
        staging = Path(work)
        pieces = download_verified_chunks(staging)
        with subprocess.Popen(
            ["/usr/bin/tar", "--zstd", "--extract", "--file", "-", "--no-same-owner",
             "--directory", str(staging)],
            stdin=subprocess.PIPE,
        ) as extract:
            for path in pieces:
                with path.open("rb") as stream:
                    shutil.copyfileobj(stream, extract.stdin, 2**20)
            extract.stdin.close()
            if extract.wait():
                raise RuntimeError("Lean archive extraction failed.")
        version = command(str(staging / NAME / "bin/lean"), "--version", capture=True)
        if "version 4.24.0," not in version:
            raise RuntimeError(f"Unexpected toolchain version: {version}")
        (staging / NAME).rename(TOOLCHAIN)
        receipt.write_text(json.dumps({"url": URL, "sha256": ARCHIVE_SHA256, "version": version}, indent=2) + "\n")
    print(version, flush=True)


def shallow_checkout(packages: Path, name: str, url: str, revision: str) -> Path:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid package name: {name}")
    if not re.fullmatch(r"https://github\.com/(leanprover-community|leanprover)/[\w.-]+", url):
        raise ValueError(f"Unexpected package source: {url}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(f"Expected an exact Git revision for {name}.")
    checkout = packages / name
    if not checkout.exists():
        with TemporaryDirectory(prefix=f"{name}-", dir=packages) as work:
            staging = Path(work)
            command("/usr/bin/git", "init", "--quiet", cwd=staging)
            command("/usr/bin/git", "remote", "add", "origin", url, cwd=staging)
            command("/usr/bin/git", "fetch", "--depth=1", "origin", revision, cwd=staging)
            command("/usr/bin/git", "checkout", "--detach", "FETCH_HEAD", cwd=staging)
            staging.rename(checkout)
    if command("/usr/bin/git", "rev-parse", "HEAD", cwd=checkout, capture=True) != revision:
        raise RuntimeError(f"The project-local {name} checkout differs from its pin.")
    if command("/usr/bin/git", "remote", "get-url", "origin", cwd=checkout, capture=True) != url:
        raise RuntimeError(f"The project-local {name} checkout has an unexpected origin.")
    return checkout


def install_mathlib():
    lean = ROOT / "lean"
    packages = lean / ".lake/packages"
    packages.mkdir(parents=True, exist_ok=True)
    checkout = shallow_checkout(packages, "mathlib", MATHLIB_URL, MATHLIB_REVISION)
    if (checkout / "lean-toolchain").read_bytes() != (lean / "lean-toolchain").read_bytes():
        raise RuntimeError("The Lean toolchain does not match the pinned Mathlib commit.")

    upstream = json.loads((checkout / "lake-manifest.json").read_text())
    inherited = [{**item, "inherited": True} for item in upstream["packages"]]
    for item in inherited:
        package = shallow_checkout(packages, item["name"], item["url"], item["rev"])
        tag = item["inputRev"]
        # Lake locates the ProofWidgets release through its official Git tag.
        if re.fullmatch(r"v[0-9][A-Za-z0-9.-]*", tag):
            ref = f"refs/tags/{tag}"
            found = subprocess.run(
                ["/usr/bin/git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
                cwd=package, capture_output=True, text=True,
            )
            if found.returncode:
                command("/usr/bin/git", "fetch", "--depth=1", "origin", f"{ref}:{ref}", cwd=package)
            if command("/usr/bin/git", "rev-parse", f"{ref}^{{commit}}", cwd=package, capture=True) != item["rev"]:
                raise RuntimeError(f"The release tag for {item['name']} differs from the pinned commit.")
    expected_manifest = {
        "version": upstream["version"], "packagesDir": ".lake/packages", "packages": [
            {"url": MATHLIB_URL, "type": "git", "subDir": None, "scope": "",
             "rev": MATHLIB_REVISION, "name": "mathlib", "manifestFile": "lake-manifest.json",
             "inputRev": MATHLIB_REVISION, "inherited": False, "configFile": "lakefile.lean"},
            *inherited,
        ], "name": "physics_lean4", "lakeDir": ".lake",
    }
    lock = lean / "lake-manifest.json"
    if lock.exists():
        if json.loads(lock.read_text()) != expected_manifest:
            raise RuntimeError("The project manifest differs from the pinned dependency set.")
    else:
        with lock.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(expected_manifest, indent=2) + "\n")

    command(str(TOOLCHAIN / "bin/lake"), "exe", "cache", "get",
            "Mathlib.Analysis.Calculus.Deriv.MeanValue",
            "Mathlib.Analysis.Calculus.Deriv.Pow",
            "Mathlib.Analysis.SpecialFunctions.Trigonometric.Deriv",
            "Mathlib.Tactic.Linarith",
            "Mathlib.Tactic.Ring",
            cwd=lean)


if __name__ == "__main__":
    install_toolchain()
    install_mathlib()
