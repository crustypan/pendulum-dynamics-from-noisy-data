# Research plan

## Research questions

Study the failure of linear approximations, the effects of observation noise and training coverage, and the mathematical guarantees that Lean 4 can establish about learned candidate dynamics.

The physical reference is the ideal undamped pendulum with theta_dot = omega and omega_dot = -k sin(theta). Gravity is 9.81 m/s^2 and length is 1 m. Initial angular velocity is zero. Each 10 s trajectory contains 501 samples at intervals of 0.02 s.

## Data splits

| Split | Initial angles in degrees |
| --- | --- |
| Training A | 5, 15, 30 |
| Training B | 5, 15, 30, 60 |
| Validation | 10, 20 |
| Test | 45, 75, 90 |

Training A and B are separate conditions with shared small-angle trajectories. Validation and test angles are excluded from each training condition. A 45-degree trajectory is extrapolation for A and interpolation in initial amplitude for B. The 75- and 90-degree trajectories are extrapolation for both conditions.

Training B increases coverage and the number of trajectories together. Its comparison with A measures their combined effect. The validation set covers small amplitudes only. These properties must be retained when interpreting later hyperparameter selection and generalization.

## Phase 1

Use SciPy DOP853 with rtol = 1e-11, atol = 1e-13 and maximum internal step = 0.1 s. Check reference physical-energy drift against 1e-8, event periods against the exact elliptic-integral benchmark within 1e-8 s, and angle changes after tighter integration tolerances against 1e-8 rad. These thresholds were fixed before server test-set evaluation.

Fit M1, theta_ddot = -a theta, M2, theta_ddot = -a sin(theta), and M3, theta_ddot = -a theta - b theta^3. Use ordinary least squares on acceleration estimated from sampled training angles. The five-point central stencil discards two samples at each end of each individual trajectory. It is applied before combining trajectories.

No reference derivative or true physical parameter enters fitting. Coefficients are unconstrained. In the cubic sign convention, the small-angle Taylor comparison gives a = k and b = -k/6. This is a local comparison, not a globally true cubic model.

Integrate all fitted models from the declared initial conditions. Report angle RMSE and period relative error per trajectory. Compare the physical coefficient with k only for M2. Keep model equations and coefficients, reference and predicted trajectories, reference checks, software versions, configuration and source hashes.

Estimate periods from consecutive descending zero crossings. Cross-check the algorithm against the linear analytic period and the nonlinear elliptic-integral period.

## Phase 2

Add independent Gaussian angle-observation noise with standard deviations 0, 0.5, 2 and 5 degrees, converted to radians. Use one noiseless run and 20 independent seeds for each nonzero noise condition.

Compare direct central differentiation with Savitzky–Golay differentiation. Select smoothing choices using validation trajectories only. Record the exact stencil, endpoint policy, candidate window sizes of 21, 31 and 41 samples, and polynomial orders before running the test evaluation.

Fit the predefined sparse library of theta, theta^3, sin(theta) and omega with validated sparse regression. Use training-derived scaling. Preserve paired noise realizations across compared methods and use distinct random streams for different observed trajectories. Record terms, coefficients, sparsity, trajectory errors and structure-selection frequency. State the numerical criterion for a selected term before examining test outcomes.

Treat repeated noisy trajectories as experiment repetitions. Consecutive time samples are dependent. Report mean and standard deviation across the independent seeds for each condition.

## Phase 3

Inspect and pin a separate compatible Lean 4 and Mathlib environment within the project root. Prove the physical-energy rate identity for trajectories satisfying theta_dot = omega and omega_dot = f(theta, omega). Specialize it to the sinusoidal and linear candidates and prove their respective conservation statements with explicit trajectory hypotheses.

The instantaneous identity requires differentiability of the trajectories at the time under consideration. A separate constancy theorem needs suitable interval, differentiability and endpoint continuity hypotheses. Evaluate candidate physical-energy drift using the fixed reference k.

Compile every claimed Lean theorem. Preserve exact verification commands and dependency revisions. Unfinished proofs remain reported as unfinished.

## Phase 4

Prepare the saved-data figures, learned-equation and metric tables, and a table of compiled formal theorems. Write a 4–6 page English report and a one-page research highlight grounded in completed experiments and proofs. Document synthetic-data limitations, candidate-library assumptions, identifiability and the scope of formal guarantees.

## Phase acceptance

Complete and verify the current phase before implementing the next. Preserve failed numerical runs and their status. Record methodological changes with their reasons before using them in reported experiments.
