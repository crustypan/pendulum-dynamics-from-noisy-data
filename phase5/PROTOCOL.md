# Phase 5 protocol

This extension asks how the training angle design and the treatment of angle noise affect identification and prediction. The two training designs use four trajectories each and replace a single release at 25° with one at 60°. The result estimates the effect of that replacement at a fixed data budget. The reference model, sampling grid, derivative baselines, sparse regression and validation rule follow v1.

| Split | Releases |
| --- | --- |
| Narrow training | 5°, 15°, 25°, 30° |
| Wide training | 5°, 15°, 30°, 60° |
| Validation | 10°, 20° |
| Test | 50°, 80°, 95° |

The primary tests are 80° and 95°, outside both training ranges. The 50° test is between the endpoints of the wide design and outside the narrow design. Validation remains at the same two small angles for all six groups. Each reference starts at rest and is sampled at 0.02 s for 10 s. Gravity divided by length is 9.81 s⁻². Only the angle series is observed during training. The known release state initializes each rollout.

One trial uses clean observations and 20 independent trials use each of 0.5°, 2° and 5° Gaussian angle noise. PCG64 derives the stream from the Phase 5 master seed, noise index, replicate seed and the index of the release in the sorted training and validation angles. All three methods receive identical observations per trial. The two training designs share observations for the three common releases.

## Candidate fits

All methods use the same four columns: angle, angle cubed, sine of the angle and angular velocity. They use the same interior centers after discarding 20 samples at each end. Direct differences use the v1 central stencils. Savitzky–Golay estimates angle, velocity and acceleration with windows of 21, 31 and 41 samples and polynomial orders 2, 3 and 4.

The weak form uses only the measured angle. In each window let the dimensionless coordinate be s in [-1, 1], and set the test function φ(s) = (1 − s²)^p, with p = 3, 4 or 5. Both φ and its first derivative vanish at each endpoint. Integration by parts puts the acceleration on the left as the integral of θ φ″ and the velocity column on the right as the integral of −θ φ′. The other columns integrate θ, θ³ and sin(θ) against φ. Derivatives of φ are with respect to time. All moments are divided by the same integral of φ. The design uses piecewise linear interpolation of the sampled angle and each sampled nonlinear feature. Gauss–Legendre quadrature integrates the resulting polynomial in each sampling interval, with p + 1 nodes. The weak window lengths match the Savitzky–Golay grid. Noise can still bias the nonlinear columns. [Weak SINDy paper](https://doi.org/10.1137/20M1343166)

All variants use v1 training RMS scaling and sequential thresholded least squares with the eight thresholds and ridge penalty in the configuration. The active support is refit without the ridge penalty. Each method selects by mean ten-second rollout angle RMSE against the two noisy validation series. Both rollouts must complete. Scores within 1e-10 rad of the minimum are tied and the tie is resolved by support size, score, then grid order. A case without an eligible candidate is retained. This gives 366 intended cases and 18,544 validation candidates. The selected table, candidate grid, input observations and code hashes are frozen before any test reference or rollout is generated.

## Outcomes and comparisons

The primary outcome is the proportion of intended 80° and 95° rollouts stopped by the v1 state limit (2π rad or 100 rad/s). Report the count and rate of other incomplete rollouts separately, including cases without an eligible candidate. All 1,098 intended tests appear in the test table, including failures. Measure angle RMSE against the clean reference and the maximum sampled relative change in physical energy for completed paths. The latter uses k = 9.81 s⁻² and the initial physical energy as the denominator. A sine-only recovery has exactly the sine column in the fitted support. Missing models are counted as non-recoveries.

Within each noise level, compare wide minus narrow for each method, and compare Savitzky–Golay minus direct, weak minus direct, and weak minus Savitzky–Golay for each training design. Pool the positive noise levels for a companion estimate. Guard and completion contrasts average the difference within each matched seed across the two primary angles. RMSE contrasts use only matching seed-angle rollouts that completed on both sides, first averaging within each eligible seed. Report both matched denominators. Report 95% percentile intervals from 10,000 paired bootstrap resamples at the seed level. The pooled resample is stratified by noise level. The clean trial has no interval. These intervals describe sampling uncertainty for this benchmark.

Re-run all 732 intended primary rollouts with tighter solver tolerances on the same sample grid. Retain the nominal run for the comparison and record changes in status, RMSE and energy drift in the tolerance audit. The existing Lean energy theorem applies to the unchanged four-term library and is used to interpret the numerical energy metric. Numerical samples describe the computed trajectories.

Freeze this protocol, the configuration and fitting code before model selection. The phase is complete when the selection archive, all planned test statuses, comparison table, two figures and reproduction checks are available.
