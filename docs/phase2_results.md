# Phase 2 results

## Verified run

The 2026-11-07 server run used the [Phase 2 protocol](phase2_protocol.md). It generated 61 independent noise-level and replicate combinations, with one noiseless repetition and 20 repetitions at each positive noise level. The two training conditions and two derivative estimators produced 244 selected SINDy models from 9,760 candidate settings. Their selection was frozen before the three test trajectories were generated.

All 31 automatic tests passed. The independent results audit regenerated the observations, checked the complete validation grid and selection rule, reloaded the saved coefficients, recalculated test RMSE from the saved trajectories and verified source and artifact hashes. The Phase 1 checks also passed against its saved outputs.

Of 732 test rollouts, 634 completed and 98 reached a predefined state limit. 595 completed rollouts had a period estimate. The test angle coverage labels and full failure counts are in [the per-angle summary](../results/noise_sindy/test_summary_by_angle.csv).

| Initial angle | Completed | State limit |
| ---: | ---: | ---: |
| 45° | 243 | 1 |
| 75° | 202 | 42 |
| 90° | 189 | 55 |

## Main results

P1 is direct three-point differentiation. P2 is Savitzky–Golay preprocessing with its window and polynomial order selected on validation trajectories. The RMSE column uses repetitions that completed all three test angles. Relative sine coefficient error is conditional on a selected sine term, with the number of qualifying seeds in parentheses. Each cell gives the mean and, when at least two observations qualify, the sample standard deviation. The exact-support denominator is the number of intended repetitions.

| Noise SD (deg) | Training | Method | All test angles completed | Exact sine-only support | Test RMSE (rad) | Relative sine coefficient error |
| ---: | :---: | :---: | ---: | ---: | ---: | ---: |
| 0 | A | P1 | 1/1 | 1/1 | 2.243e-3 | 3.182e-4 (1) |
| 0 | A | P2 | 1/1 | 1/1 | 1.483e-3 | 2.104e-4 (1) |
| 0 | B | P1 | 1/1 | 1/1 | 2.118e-3 | 3.004e-4 (1) |
| 0 | B | P2 | 1/1 | 1/1 | 1.517e-3 | 2.152e-4 (1) |
| 0.5 | A | P1 | 10/20 | 0/20 | 1.1604 ± 0.0322 | 2.971e+4 ± 3.768e+3 (20) |
| 0.5 | A | P2 | 20/20 | 15/20 | 0.2912 ± 0.5011 | 33.3404 ± 79.6255 (20) |
| 0.5 | B | P1 | 20/20 | 0/20 | 1.1318 ± 0.0901 | 543.6072 ± 77.6008 (20) |
| 0.5 | B | P2 | 20/20 | 7/20 | 0.3269 ± 0.3161 | 4.7408 ± 4.8779 (20) |
| 2 | A | P1 | 0/20 | 0/20 | — | 2.270e+5 ± 1.653e+4 (20) |
| 2 | A | P2 | 18/20 | 4/20 | 0.9333 ± 0.4873 | 522.3690 ± 451.5723 (20) |
| 2 | B | P1 | 20/20 | 0/20 | 1.2670 ± 0.0138 | 6.827e+3 ± 805.0034 (20) |
| 2 | B | P2 | 17/20 | 4/20 | 0.6498 ± 0.3718 | 18.0958 ± 11.9672 (20) |
| 5 | A | P1 | 0/20 | 0/20 | — | 2.462e+5 ± 5.463e+4 (20) |
| 5 | A | P2 | 20/20 | 0/20 | 1.1793 ± 0.0359 | 1.281e+3 ± 1.386e+3 (20) |
| 5 | B | P1 | 20/20 | 0/20 | 1.2548 ± 0.0321 | 2.141e+4 ± 2.359e+3 (20) |
| 5 | B | P2 | 20/20 | 1/20 | 0.6829 ± 0.2725 | 17.8084 ± 12.3311 (20) |

## Interpretation

### Derivative estimation and test prediction

At 2 degrees of noise, the Training B validation acceleration RMSE was 211.72 rad/s² for P1 and 1.17 rad/s² for P2. Independent angle noise of standard deviation sigma contributes a standard deviation of sqrt(6) times sigma divided by dt squared to a three-point second difference. For the 2-degree condition this gives about 213.8 rad/s² at dt = 0.02 s.

In Training B at 5 degrees, both methods completed all 20 paired repetitions. The average test angle RMSE was 1.255 rad for P1 and 0.683 rad for P2. The paired difference P2 minus P1 was -0.572 ± 0.289 rad. At 2 degrees, the corresponding mean difference was -0.617 rad across the 17 pairs that both completed. The completion denominator is relevant because the eligible seeds differ in some conditions.

### Structure and coefficient recovery

All four noiseless fits recovered the sine-only support. Across noisy conditions, exact recovery was 0/120 for P1 and 31/120 for P2. At 0.5 degrees with P2, the exact support appeared in 15/20 Training A fits and 7/20 Training B fits. With exact support, the mean relative sine coefficient errors in those cells were 1.435e-3 and 6.863e-4, respectively.

Every noisy fit retained a sine term. Many fits also retained polynomial or velocity terms, and their coefficients could compensate for one another. For example, Training A, P1, noise SD 5 degrees and seed 16 produced a theta coefficient of approximately +3.52e6 and a sine coefficient of approximately -3.52e6. The sine-only recovery rate and the relative coefficient errors describe different aspects of that behavior.

### Coverage and collinearity

In the noiseless P1 design, the theta/sine correlation was 0.999885 for Training A and 0.997906 for Training B. The respective scaled library condition numbers were approximately 5.165e+4 and 3.100e+3. Wider training coverage improved this diagnostic while its effect on exact support varied by noise level. Training B changes both the angle range and the number of trajectories. The validation angles remain 10 and 20 degrees.

The 45-degree test lies within Training B's initial-angle range and beyond Training A's range. The 75- and 90-degree cases extrapolate from either training condition and accounted for 97 of the 98 state-limit stops.

## Figures and files

[Noise robustness](../figures/noise_sindy/noise_robustness.png) shows the mean test error for completed repetitions, exact-support frequencies with 95% Wilson intervals at positive noise, conditional coefficient error, and completion rates. Gaps in the test error indicate cells without a fully completed repetition.

[Derivative estimation](../figures/noise_sindy/derivative_estimation.png) shows velocity and acceleration RMSE on the validation angles for Training B. The displayed points average the two angles within each seed and then average across seeds.

| File | Contents |
| --- | --- |
| [summary.csv](../results/noise_sindy/summary.csv) | All 16 cells, including means, sample SDs, counts, correlations and support intervals |
| [selected_models.csv](../results/noise_sindy/selected_models.csv) | Frozen coefficients, equations, support, chosen settings and validation errors |
| [validation_grid.csv.gz](../results/noise_sindy/validation_grid.csv.gz) | Every candidate setting and validation score or failure |
| [test_metrics.csv](../results/noise_sindy/test_metrics.csv) and [test_predictions.npz](../results/noise_sindy/test_predictions.npz) | Test angle, status, coverage, errors and sampled predictions, joined by prediction_index |
| [observations.npz](../results/noise_sindy/observations.npz), [reference.npz](../results/noise_sindy/reference.npz) and [trials.csv](../results/noise_sindy/trials.csv) | Angle observations, reference states, sample times and replicate identifiers |
| [support_frequencies.csv](../results/noise_sindy/support_frequencies.csv) and [paired_comparisons.csv](../results/noise_sindy/paired_comparisons.csv) | Exact support patterns and matched-seed test error contrasts |
| [derivative_metrics.csv](../results/noise_sindy/derivative_metrics.csv) | Per-model and validation-angle derivative diagnostics |

The run folder also contains the configuration snapshots, the selection hash, package versions, source hashes and the artifact checksum manifest. Incomplete rollouts have blank scalar errors and NaN prediction arrays.

## Reproduce

Run from the project root using the project virtual environment.

```bash
python3 -B scripts/run_isolated.py -- .venv/bin/python -m pytest -q
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/run_noise_experiments.py --output results/noise_sindy_reproduction --figures figures/noise_sindy_reproduction
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/verify_noise_results.py --results results/noise_sindy_reproduction
```
