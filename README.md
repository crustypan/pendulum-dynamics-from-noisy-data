# Learning Nonlinear Pendulum Dynamics from Noisy Data

This independent research project asks whether a dynamical model learned from noisy angles can predict an unseen trajectory and satisfy the physical energy law. It compares pendulum baselines, tests sparse identification of nonlinear dynamics (SINDy), and uses Lean 4 to prove how the fitted acceleration changes the reference energy.

- [Six-page English research report](report/pdf/research_report.pdf) · [editable source](report/research_report.md)
- [One-page Research Highlight](report/pdf/research_highlight.pdf) · [editable source](report/research_highlight.md)
- [Figure and evidence index](report/README.md) · [Data and proof guide](docs/artifact_index.md)

All observations are synthetic. The candidate library includes the sine term. Support recovery measures whether the method selects that supplied term without extra terms.

## What the study found

- **Phase 1 — baselines.** The fitted sine model has a mean held-out angle RMSE of about 1.1e-6 rad. The linear model's own energy is conserved in its exact dynamics, while its sampled physical energy varies by 20.0% at a 90° release in Training A.
- **Phase 2 — noisy identification.** Savitzky–Golay preprocessing recovers the sine-only support in 31 of 120 noisy fits; direct central differences recover it in 0 of 120. Of 732 held-out rollouts, 634 complete and 98 reach a state limit.
- **Phase 3 — formal verification.** Lean checks the physical energy rate, interval conservation and the exact coefficient condition for zero physical energy rate at every state. The 13-theorem audit covers the 244 archived models through an indexed theorem. All 634 completed pairs pass the shared-grid solver comparison.
- **Phase 4 — failure analysis.** Both solver settings reproduce the speed guard in all 98 stopped rollouts. There are 97 stops at 75° or 90°, and 85 stops occur with zero or negative velocity coefficients. The [analysis](docs/phase4_failure_analysis.md) traces examples to derivative noise, weak separation of library terms and incorrect extrapolated acceleration.

## Repository map

| Path | Purpose |
| --- | --- |
| `configs/baseline.json`, `configs/noise.json`, `configs/energy.json` | Physical reference, data splits, random seeds, fit grid and integration settings |
| `src/pendulum_research/` | Reference simulation, preprocessing, sparse fitting, model evaluation, and energy analysis |
| `scripts/run_baseline.py`, `scripts/run_noise_experiments.py` | Generate Phases 1 and 2, including coefficients, predictions and figures |
| `scripts/run_energy_analysis.py`, `scripts/run_failure_diagnostics.py` | Replay frozen equations for physical energy and guard analysis |
| `scripts/verify_*.py`, `tests/` | Check archived artifacts, mathematical and numerical results, and report builds |
| `lean/Pendulum/Energy.lean`, `lean/Pendulum/FrozenModels.lean` | General energy proofs and their specialization to the frozen coefficient table |
| `lean/Audit.lean`, `lean/lean-toolchain`, `lean/lake-manifest.json` | Theorem dependency audit and exact Lean/Mathlib pins |
| `results/` | Coefficients, traces, metrics, checksums and verification records; see the [data guide](docs/artifact_index.md) |
| `figures/` | Seven full-size figures generated from the saved experiments |
| `report/` | Both PDFs, editable Markdown and the reproducible build receipt |
| `docs/` | [Study plan](docs/research_plan.md), [experiment log](docs/experiment_log.md), [research decisions](docs/research_decisions.md), and phase protocols |

## Reproduce the results

Use Python 3.10 with the pinned dependencies. The verified Linux setup uses Bubblewrap and a user systemd session. The runner limits jobs to 50% of one CPU core and 1 GiB of memory. It uses the project for writable files and runs offline, with network access explicitly enabled for dependency setup. The pinned Lean installer is for Linux x86-64. The PDF build uses the Linux Lato and DejaVu fonts.

Run these commands from the repository root. Keep the archived output directories unchanged.

```bash
python3 -B scripts/run_isolated.py -- python3 -I -B -m venv .venv
python3 -B scripts/run_isolated.py --network -- .venv/bin/python -m pip install -r requirements-lock.txt
python3 -B scripts/run_isolated.py --network -- .venv/bin/python -m pip install --no-deps --no-build-isolation -e .
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/check_isolation.py
python3 -B scripts/run_isolated.py -- .venv/bin/python -m pytest -q
```

### Numerical experiments

The examples below write new results under the ignored `.tmp/reproduce/` directory. Use a new output directory on subsequent runs. Phases 3 and 4 intentionally analyze the frozen artifacts included with this repository.

```bash
# Phase 1: noiseless simulation and baselines
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/run_baseline.py \
  --output .tmp/reproduce/baseline --figures .tmp/reproduce/fig_baseline
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/verify_saved_run.py \
  --results .tmp/reproduce/baseline

# Phase 2: noisy observations, validation selection and test rollouts
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/run_noise_experiments.py \
  --output .tmp/reproduce/noise --figures .tmp/reproduce/fig_noise
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/verify_noise_results.py \
  --results .tmp/reproduce/noise

# Phase 3: physical energy drift and tighter integration
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/run_energy_analysis.py \
  --output .tmp/reproduce/energy --figures .tmp/reproduce/fig_energy
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/verify_energy_analysis.py \
  --results .tmp/reproduce/energy

# Phase 4: terminal events from the archived SINDy equations
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/run_failure_diagnostics.py \
  --output .tmp/reproduce/failures --figures .tmp/reproduce/fig_failures
```

### Lean 4 and Mathlib

The installer verifies the official Lean 4.24.0 release archive and fetches the Mathlib revisions pinned in the Lake manifest. The exact rational coefficients in Lean are checked against the frozen Phase 2 CSV.

```bash
python3 -B scripts/run_lean.py --network -- /usr/bin/python3 -B scripts/install_lean.py
python3 -B scripts/verify_lean.py --output .tmp/reproduce/lean_verification
```

The [saved proof audit](results/lean_verification/verification.json) lists the compiler versions, source hashes, package revisions and theorem dependencies. The formal guarantees apply to exact trajectories satisfying the stated hypotheses. Sampled drift is a numerical diagnostic.

### PDFs and archive verification

```bash
python3 -B scripts/run_isolated.py --network -- .venv/bin/python -m pip install \
  --only-binary=:all: --no-deps --target .tools/report-packages -r requirements-report-lock.txt
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/build_phase4_reports.py \
  --output .tmp/reproduce/pdf
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/verify_phase4.py
```

See the [Phase 4 checks](results/phase4_checks) for test, Lean, archive and PDF verification. The dependency installations, compiled Lean cache, virtual environments, and temporary files are excluded from version control.
