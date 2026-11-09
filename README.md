# Learning Nonlinear Pendulum Dynamics from Noisy Data

This independent research project asks whether a dynamical model learned from noisy angles can predict an unseen trajectory and satisfy the physical energy law. It compares pendulum baselines, tests sparse identification of nonlinear dynamics (SINDy), and uses Lean 4 to prove how the fitted acceleration changes the reference energy.

- [v1 release · Phases 1–4](https://github.com/crustypan/physics-lean4/releases/tag/v1) · [Phase 5 results and figures](phase5/RESULTS.md)
- [Six-page English research report](report/pdf/research_report.pdf) · [editable source](report/research_report.md)
- [One-page Research Highlight](report/pdf/research_highlight.pdf) · [editable source](report/research_highlight.md)
- [Figure and evidence index](report/README.md) · [Data and proof guide](docs/artifact_index.md)

All observations are synthetic. The candidate library includes the sine term. Support recovery measures whether the method selects that supplied term without extra terms.

## Results at a glance

Click any figure to open the full-size PNG.

### Phase 5. Training-angle coverage and weak-form SINDy

Each design uses four training trajectories. The narrow design uses 5°, 15°, 25° and 30°. The wide design replaces 25° with 60°. Model selection uses separate 10° and 20° validation runs. The new 50°, 80° and 95° releases are evaluated after selection is frozen.

The table pools the three noisy conditions at the primary 80° and 95° releases, outside both training ranges.

| Method | State-limit stops, narrow | State-limit stops, wide | Sine-only models, narrow | Sine-only models, wide |
| --- | ---: | ---: | ---: | ---: |
| Direct differences | 88/120 | 0/120 | 0/60 | 0/60 |
| Savitzky–Golay | 11/120 | 2/120 | 19/60 | 15/60 |
| Weak form | 8/120 | 2/120 | 31/60 | 25/60 |

[![State-limit stops and sine-only recovery by noise level and training design](phase5/results/main/figures/benchmark_outcomes.png)](phase5/results/main/figures/benchmark_outcomes.png)

Among matched trajectories that both methods completed, weak-form SINDy reduced the mean angle RMSE relative to Savitzky–Golay by 0.325 rad in the narrow design and 0.170 rad in the wide design. The wide direct-difference fits completed all 120 primary tests, with a median maximum physical energy deviation of 39.24 times the initial energy.

[![Paired differences in state-limit stops and angle RMSE with 95% bootstrap intervals](phase5/results/main/figures/paired_effects.png)](phase5/results/main/figures/paired_effects.png)

The complete archive includes all 1,098 test outcomes and 732 tighter-tolerance checks. [Phase 5 report](phase5/RESULTS.md) · [95° trajectory and energy example](phase5/results/main/figures/heldout_example.png) · [Paired comparison table](phase5/results/main/paired_contrasts.csv)

### 1. Predicting motion at unseen release angles

[![Held-out angle RMSE for linear, sine and cubic pendulum models at 45, 75 and 90 degrees](figures/baseline/test_rmse.png)](figures/baseline/test_rmse.png)

The fitted sine model averages about 1.1–1.2 × 10⁻⁶ rad in held-out angle RMSE. The linear and cubic fits have larger errors at higher release angles.

### 2. Recovering an equation from noisy angles

[![Noise robustness of SINDy showing test error, sine-only recovery, coefficient error and completion](figures/noise_sindy/noise_robustness.png)](figures/noise_sindy/noise_robustness.png)

Of 120 noisy fits per method, Savitzky–Golay recovered sine-only support in 31; central differences recovered it in 0. The test RMSE panel includes only seeds that completed all three test angles.

### 3. Comparing fitted and physical energy

[![At 90 degrees the linear model has small variation in its own energy and large variation in physical energy](figures/energy_drift/baseline_conservation.png)](figures/energy_drift/baseline_conservation.png)

At 90° with Training A, the linear model's own energy changes by at most 4.16 × 10⁻¹¹ of its initial value in the sampled trajectory. The corresponding physical energy change is 20.0%. See the [Lean energy proofs](lean/Pendulum/Energy.lean) and [SINDy drift comparison](figures/energy_drift/physical_energy_drift.png).

### 4. Diagnosing failed SINDy predictions

[![Fitted and reference release accelerations and guard stops by held-out release angle](figures/failure_diagnostics/failure_mechanisms.png)](figures/failure_diagnostics/failure_mechanisms.png)

Both solver settings reproduced the 100 rad/s speed limit in all 98 stopped rollouts; 97 began at 75° or 90°. The left panel shows a fit that predicts outward acceleration at 90° despite low validation error.

See the [figure and evidence index](report/README.md#figure-and-evidence-index) for the other plots and their source data.

## What v1 found

- **Phase 1 — baselines.** The fitted sine model has a mean held-out angle RMSE of about 1.1e-6 rad. The linear model's own energy is conserved in its exact dynamics, while its sampled physical energy varies by 20.0% at a 90° release in Training A.
- **Phase 2 — noisy identification.** Savitzky–Golay preprocessing recovers the sine-only support in 31 of 120 noisy fits; direct central differences recover it in 0 of 120. Of 732 held-out rollouts, 634 complete and 98 reach a state limit.
- **Phase 3 — formal verification.** Lean checks the physical energy rate, interval conservation and the exact coefficient condition for zero physical energy rate at every state. The 13-theorem audit covers the 244 archived models through an indexed theorem. All 634 completed pairs pass the shared-grid solver comparison.
- **Phase 4 — failure analysis.** Both solver settings reproduce the speed guard in all 98 stopped rollouts. There are 97 stops at 75° or 90°, and 85 stops occur with zero or negative velocity coefficients. The [analysis](docs/phase4_failure_analysis.md) traces examples to derivative noise, weak separation of library terms and incorrect extrapolated acceleration.

## Repository map

| Path | Purpose |
| --- | --- |
| `phase5/` | Coverage and noise comparison, weak-form implementation, figures, results and verification |
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

### Phase 5 benchmark

Use the Python environment set up above. Run the four stages in order from the repository root. The archived results are in `phase5/results/main/`. Use a new run name under `phase5/results/` to reproduce the experiment.

```bash
run=phase5/results/reproduction
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/experiment.py fit --run-dir "$run"
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/experiment.py evaluate --run-dir "$run"
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/report.py --run-dir "$run"
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/verify.py --run-dir "$run" --replay-trial 21
```

The fit stage freezes the candidate and selected-model records. The evaluation stage verifies that freeze before generating the new test releases. The verification stage checks the saved trajectories and tables and refits one noisy trial. [Phase 5 protocol](phase5/PROTOCOL.md) · [Portable Python setup and artifact index](phase5/README.md)

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
