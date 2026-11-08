# Experiment log

## 2026-11-07

The project plan and the shared background discussion were reviewed. The SSH connection and empty project directory were verified.

A process-isolation probe succeeded with Bubblewrap and a user systemd scope. The project directory was visible inside the sandbox. The account home, existing research directory and GPU device were outside its mounted view.

A local in-memory numerical preflight used NumPy 1.23.5 and SciPy 1.10.0. Its linear analytic-solution check had a maximum angle error of 1.31542e-11 rad. Nonlinear reference checks covered 5, 15, 30, 60 and 90 degrees. Server experiment results will be recorded after installation and execution.

## Verified server Phase 1

Execution date is 2026-11-07. The installed environment uses Python 3.10.12, NumPy 2.2.6, SciPy 1.15.3, Matplotlib 3.10.9 and Pytest 9.2.0. Exact dependencies are recorded in requirements-lock.txt.

All 24 automatic tests passed. The saved-run checker reloaded all 6 model records, recalculated the RMSE of all 51 saved trajectory comparisons and verified 14 source hashes. Nine reference trajectories contain 501 samples each.

The maximum reference relative energy drift was 4.88010644437e-11. The maximum event-period absolute error against the elliptic-integral benchmark was 1.523670079e-12 s. Tighter-tolerance agreement also passed for every reference trajectory.

| Training condition | Model | a | b | Mean test RMSE (rad) | Mean test period relative error |
| --- | --- | --- | --- | --- | --- |
| Training A | M1 | 9.535493723 | — | 1.07303664 | 0.0863043298 |
| Training A | M2 | 9.809998365 | — | 1.17520655e-06 | 8.33491256e-08 |
| Training A | M3 | 9.808790161 | -1.610214672 | 0.147878999 | 0.00921984087 |
| Training B | M1 | 8.755091713 | — | 0.8421958 | 0.0583485851 |
| Training B | M2 | 9.809998467 | — | 1.10161982e-06 | 7.81301479e-08 |
| Training B | M3 | 9.792630857 | -1.539307695 | 0.0741058208 | 0.0045441921 |

The mean test errors above average the three held-out initial amplitudes of 45, 75 and 90 degrees. They are deterministic noiseless results and carry no across-seed uncertainty estimate.

At 90 degrees under Training A, M1 has an angle RMSE of 1.73025326 rad, M2 has 1.42970803e-6 rad and M3 has 0.321936716 rad. The observed linear error is associated with accumulated phase mismatch. Extending the training set reduces the mean test RMSE of the linear and cubic models. The comparison combines wider initial-angle coverage with one additional training trajectory.

M2 uses a supplied sinusoidal candidate structure. Its fitted coefficient is approximately 9.809998 s^-2. These results quantify parameter recovery within that specified family. The cubic coefficients and the physical sign convention are retained exactly in models.json.

### Runtime verification

The resource controller reported CPUQuotaPerSecUSec = 500ms, CPUWeight = 1, MemoryMax = 1073741824 bytes, MemorySwapMax = 0 and TasksMax = 32. The filesystem probe permitted a project scratch write and rejected a write outside the project. The process namespace exposed the isolated project and system libraries, with networking and GPU devices excluded for experiment execution.

The project root has owner-only permissions. This is process isolation with resource limits on a shared research server.

### Engineering checks

The complete saved-equation format was included in model reload tests. Figure generation uses read-only system font configuration. The reviewed trajectory figure separates its title and legend. Initial engineering outputs are preserved in the private, Git-ignored diagnostic directory.

### Reproduction commands

Run these commands from the project root.

```bash
python3 -B scripts/run_isolated.py -- .venv/bin/python -m pytest -q
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/run_baseline.py --output results/reproduction --figures figures/reproduction
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/verify_saved_run.py --results results/reproduction
```

### Remaining phases

Phase 2 covers noisy observations and sparse identification. Phase 3 covers the isolated Lean 4 and Mathlib installation and compiled proofs. Phase 4 covers the full English report and research highlight.

## Phase 2 server run on 2026-11-07

Completed the angle-noise and SINDy study under the project filesystem sandbox, with 50% of one CPU core and a 1 GiB memory limit. Reused the locked project environment. All 31 tests passed.

Audited 61 regenerated observation trials, 9,760 validation settings, 244 frozen selected models and 732 test rollouts. 634 rollouts completed and 98 reached a state limit. The Phase 1 source and artifact checks passed again.

The [Phase 2 results](phase2_results.md) record the observed errors, support frequencies, completion counts, figures and reproduction commands. The [Phase 2 protocol](phase2_protocol.md) records the selection rules used before testing.

## Phase 3 server run on 2026-11-07

Lean 4.24.0 and Mathlib revision `f897ebcf72cd16f89ab4577d0c826cd14afaafc7` were installed under the project root. A full-history Git fetch hit the existing per-file limit; shallow fetches of the exact locked revisions worked within that limit. The [successful compiler transcript](../results/lean_verification/compile_transcript.log) and [axiom audit](../results/lean_verification/axioms.log) record the completed proofs, including the model table linked to all 244 frozen equations.

All 38 tests passed. The tightened solver reproduced the status of every rollout: 634 complete and 98 state-limit stops. All complete pairs passed the shared-grid drift comparison. The largest shift from refining the sampling grid alone was 6.684 in the dimensionless drift metric. The saved-energy, Phase 1, Phase 2 and isolation audits passed.

See the [Phase 3 results](phase3_results.md) for the theorem hypotheses, interpretation and exact artifact paths, and the [protocol](phase3_protocol.md) for the settings used before measuring drift.

## Phase 4 server run on 2026-11-07

Checked the saved Phase 1 to Phase 3 artifacts, replayed the 98 frozen SINDy state-limit cases under both original and tightened tolerances, and saved release acceleration diagnostics for all 732 cases. Every replay reached the 100 rad/s speed limit; 97 stops occurred at 75° or 90°. The greatest change in event time between solver settings was 3.15e-10 s.

The [failure analysis](phase4_failure_analysis.md) records the observed failure modes and links each example to the frozen coefficients and guard events. The [report package](../report/README.md) contains a six-page English research report and a one-page Research Highlight, both as PDF and editable Markdown. Page counts, hashes and verification records are preserved with the deliverables.
