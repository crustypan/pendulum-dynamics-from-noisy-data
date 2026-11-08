# Research decisions

## 2026-11-07

### Project location and runtime boundary

Use the existing physics-lean4 directory as the repository root. Store its virtual environment, caches, temporary files, source and outputs below that root. Use Bubblewrap with a user systemd scope, a CPU quota of 50% of one core, a 1 GiB memory limit and one numerical-library thread. Installation is the explicit network-enabled operation.

### Clean derivative estimator

Choose a five-point central second derivative for Phase 1. In a local in-memory design check on Training A, the three-point stencil gave M2 a relative coefficient error of approximately 3.18744e-4. The five-point stencil reduced this to approximately 1.66700e-7. These are preprocessing checks from an existing local Python environment, not the server baseline results.

This choice reduces the clean derivative approximation error while retaining the angle-only observation constraint. It discards two samples per boundary. Phase 2 retains its planned direct-differentiation and Savitzky–Golay comparison.

### Coefficient interpretation

Fit all coefficients from data. Report physical parameter error for M2, whose structure is the physical reference family. M1 and M3 coefficients describe their own approximations. The cubic Taylor sign is b = -k/6 in the declared equation. A negative b can make the cubic potential unbounded outside its relevant local regime.

### Reference period and solver error

Use same-direction event crossings and verify them against an independent elliptic-integral period. Use stable physical-energy evaluation and a tighter-tolerance convergence check. Evaluate held-out model trajectories only after these choices and the baseline configuration are fixed.

### Coverage and sample count

Training B adds a 60-degree trajectory to Training A. Interpret the comparison as the joint effect of wider coverage and additional data. The small-angle validation set remains part of the specified design. A pure coverage-only causal comparison would require a separately documented control in a later stage.

### Formal proof scope

Keep numerical checks and Lean compilation records distinct. The rate identity is a statement about differentiable trajectories satisfying the candidate dynamics. Constancy over an interval requires an additional theorem.

## Phase 2 protocol decisions on 2026-11-07

Use three-point central derivatives for P1 and Savitzky–Golay derivatives for P2. Compare them over the common interior samples. Pair noise realizations across methods and training sets, and select smoothing and threshold parameters by validation rollout error on the observed angles.

Use a training-scaled STLSQ implementation in the existing NumPy and SciPy environment. Freeze the chosen models before evaluation. Record guard stops separately and condition the three-angle mean error on completing all three rollouts. Details and the fixed grid are in the [Phase 2 protocol](phase2_protocol.md).

## Phase 3 protocol decisions on 2026-11-07

Use the reference coefficient 9.81 in the physical energy for every model. Measure each fitted model's own energy separately. Keep the original archived equations and test statuses; recompute them with a tighter solver and compare on the original sample times before quantifying the effect of finer sampling. Treat guard stops as incomplete and show completion counts alongside statistics over completed trajectories.

Use exact rational reals to transfer the archived decimal SINDy coefficients to Lean. Keep the conditional derivative theorem, the interval conservation result, the exact all-state coefficient test and the floating-point trajectory diagnostics distinct. Pin the Lean release and all Mathlib dependencies inside the project, using shallow Git fetches to respect the existing file limit. See the [Phase 3 protocol](phase3_protocol.md).

## Phase 4 synthesis decisions on 2026-11-07

Use post hoc diagnostics on frozen models to explain the existing evaluation. Preserve model selection, test angles and results. Reuse the original terminal guard and compare event state and time at both recorded solver settings. Select examples by lowest validation RMSE among stopped models and by largest opposing linear/sine coefficients, and report cohort counts with both examples.

Keep the report and application highlight as editable Markdown with a pinned PDF build. Include experiment outputs, proof receipts and figures in the reviewable repository tree. Store the separate PDF build dependencies and temporary renders under ignored project directories.
