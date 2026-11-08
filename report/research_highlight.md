# Learning Physics from Noisy Data

### Nonlinear pendulum dynamics and formal verification in Lean 4

> **Research question.** Can an interpretable model learned from noisy angle measurements predict unseen motion and satisfy the underlying energy law?

<!-- table-widths: 1, 1, 1 -->
| 244 frozen equations | 732 held-out rollouts | 13 audited Lean theorems |
| --- | --- | --- |
| Sparse fits across two training sets and two estimators | Tests at 45°, 75° and 90° | Exact rate identities and interval conservation |

## Approach

I used a frictionless pendulum as a benchmark with a known law. After comparing linear, sinusoidal and cubic baselines, I used sparse identification of nonlinear dynamics (SINDy) to fit equations from angles with Gaussian noise up to 5° SD. I froze selection before testing unseen initial conditions and used Lean 4 to connect the learned acceleration to physical energy.

## What the results show

**Learning from noise.** Savitzky-Golay preprocessing recovered the sine-only structure in 31 of 120 noisy fits, compared with 0 of 120 for central differences. At 5° noise with the broader training set, mean held-out angle RMSE fell from 1.255 to 0.683 rad across 20 matched repetitions. The sine function was supplied in the candidate library.

**Diagnosing failure.** Of 732 rollouts, 98 hit the speed guard under both solver settings. In one case a model with validation error of 0.0407 rad predicted outward acceleration at a 90° release, where gravity should restore the pendulum. The discrepancy exposed a failure of extrapolation from small-angle validation.

**Connecting learning and proof.** Lean proves the general rate dE/dt = ω[f(θ, ω) + k sin θ] and ideal interval conservation. The linear baseline at 90° conserved its own model energy to numerical precision while its true-reference energy varied by about 20%. This is why trajectory accuracy, energy consistency and formal claims were assessed separately.

## Research direction

This benchmark uses synthetic data. I would next broaden validation amplitudes, compare integral identification and test energy constraints on independently measured trajectories.

> **Reproducible record.** The companion project contains the [full research report](research_report.md), [Lean proofs](../lean/Pendulum), [frozen model coefficients](../results/noise_sindy/selected_models.csv) and [experiment records](../docs/experiment_log.md).
