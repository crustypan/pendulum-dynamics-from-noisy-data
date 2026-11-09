# Phase 5 · Angle coverage and noise treatment

This extension compares two four-trajectory training designs and three SINDy formulations on the simulated undamped pendulum. It uses the Phase 1–4 physics, sparse regression and guarded solver. The Phase 1–4 project is retained as v1.

Start with the [findings and comparison tables](RESULTS.md) and the [frozen protocol](PROTOCOL.md). The benchmark uses 50°, 80° and 95° releases unseen during training and validation. The primary comparison uses the two angles outside both training ranges, 80° and 95°.

## Files

| File or directory | Purpose |
| --- | --- |
| [PROTOCOL.md](PROTOCOL.md), [config.json](config.json) | Fixed angle and seed splits, estimation grids, outcomes and numerical tolerances |
| [experiment.py](experiment.py), [weak.py](weak.py) | Reproducible angle-only observations, candidate fitting, model freeze and test evaluation |
| [report.py](report.py), [verify.py](verify.py) | Group and paired statistics, figures and archive checks |
| [run_isolated.py](run_isolated.py) | Linux lab launcher with the v1 tree and virtual environment mounted read-only |
| [results/main/group_summary.csv](results/main/group_summary.csv) | Primary metrics by training design, method and noise level |
| [results/main/by_release.csv](results/main/by_release.csv) | Test outcomes for 50°, 80° and 95° separately |
| [results/main/paired_contrasts.csv](results/main/paired_contrasts.csv) | All paired estimates, 95% bootstrap intervals and matched sample sizes |
| [results/main/model_metrics.csv](results/main/model_metrics.csv), [results/main/test_metrics.csv](results/main/test_metrics.csv) | Model-level recovery metrics and every planned test status, including incomplete tests |
| [results/main/figures/](results/main/figures/) | Benchmark rates, paired effects and a fixed 95° example |
| [results/main/selected_models.csv](results/main/selected_models.csv), [results/main/candidates.csv](results/main/candidates.csv) | Exact fitted coefficients, diagnostics, candidate scores and selection flags |
| [results/main/tolerance_audit.csv](results/main/tolerance_audit.csv), [results/main/numerical_summary.json](results/main/numerical_summary.json) | Tighter-tolerance comparison for every primary test |
| [results/main/selection_frozen.json](results/main/selection_frozen.json), [results/main/evaluation_manifest.json](results/main/evaluation_manifest.json), [results/main/verification.json](results/main/verification.json) | SHA-256 manifests, stage counts and verification checks |
| [results/main/observations.npz](results/main/observations.npz), [results/main/test_reference.npz](results/main/test_reference.npz), [results/main/test_predictions.npz](results/main/test_predictions.npz) | Synthetic training and validation angles, clean test reference states and model paths |
| [v1 energy proof](../lean/Pendulum/Energy.lean) | Formal energy derivative and conservation results for the shared library |

All angles in file names, data splits and release labels use degrees. Sampled trajectories, fitted states and RMSE use radians and seconds. In the observation archive `theta_obs_rad` is indexed by trial, release and time. Join its first axis to [trials.csv](results/main/trials.csv) and its second axis to `angle_deg`. The predictions archive uses `prediction_index` from `test_metrics.csv` as its row index. Paths that did not finish have NaN arrays and a status in the CSV. The training residual in `candidates.csv` is measured on the regression target. For weak fits this target is a normalized acceleration moment, so the column represents a different residual from the pointwise methods.

## Reproduce

Run the commands from the `physics-lean4` root. They write to a fresh run directory and preserve the checked `results/main` archive. Leave the four stages in order. The test stage checks the frozen fit and generates the three fresh reference trajectories only after that check.

On the lab server, use the existing v1 Python environment and the isolated launcher. The launcher requires Linux with Bubblewrap, unprivileged user namespaces and a systemd user manager. It places temporary files and caches inside `phase5/` and limits the job to half of one CPU core and 1 GiB of memory.

```sh
run=phase5/results/reproduction
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/experiment.py fit --run-dir "$run"
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/experiment.py evaluate --run-dir "$run"
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/report.py --run-dir "$run"
python3 -B phase5/run_isolated.py -- .venv/bin/python -B phase5/verify.py --run-dir "$run" --replay-trial 21
```

On a personal POSIX machine, use a separate Python 3.10 environment inside the extension and run the same stages from the project root. The exact package versions come from the [v1 lock file](../requirements-lock.txt).

```sh
python3.10 -m venv phase5/.venv
phase5/.venv/bin/python -m pip install -r requirements-lock.txt
mkdir -p phase5/.tmp phase5/.cache/matplotlib
export PYTHONPATH="$PWD/src" PYTHONNOUSERSITE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export TMPDIR="$PWD/phase5/.tmp" MPLCONFIGDIR="$PWD/phase5/.cache/matplotlib"
run=phase5/results/reproduction
phase5/.venv/bin/python -B phase5/experiment.py fit --run-dir "$run"
phase5/.venv/bin/python -B phase5/experiment.py evaluate --run-dir "$run"
phase5/.venv/bin/python -B phase5/report.py --run-dir "$run"
phase5/.venv/bin/python -B phase5/verify.py --run-dir "$run" --replay-trial 21
```

Verification regenerates the observations, checks all 18,544 candidate records and 366 selection decisions, and recalculates the angle and energy errors from saved paths. The optional replay refits one noisy trial from its archived observations. A complete run includes 1,098 test rows and 732 tighter-tolerance audit rows. The SHA-256 manifests check each run's own files. Numerical results and plot bytes can vary across platforms.

Only the source, protocol, checked data and figures are needed to read the archive. The existing Git ignore rules exclude environments, caches, local logs and resumable fit checkpoints.
