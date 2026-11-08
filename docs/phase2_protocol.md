# Phase 2 protocol

## Design

The four measurement noise levels are 0, 0.5, 2 and 5 degrees of standard deviation. Use one noiseless repetition and 20 independent repetitions at each positive level. Gaussian errors enter the recorded angle. Initial angles and zero release velocity are controlled conditions. Use the Phase 1 train, validation and test initial angles and time grid.

At each noise level and seed, generate one angle observation for each distinct training or validation trajectory. Both training conditions and both estimators share the realizations for their common angles. Use NumPy PCG64 with a SeedSequence containing the master seed, noise-level index, replicate seed and index in the sorted observation angles. The test error compares a held-out simulation with the noiseless reference at the same initial condition.

## Derivative estimates

P1 uses raw angle with three-point central first and second differences. P2 uses Savitzky–Golay estimates of angle, velocity and acceleration from the same observed series. Search windows of 21, 31 and 41 samples and orders 2, 3 and 4. Both methods use the same interior times, with 20 samples removed at each end. Apply each derivative operator within a trajectory. [SciPy Savitzky–Golay documentation](https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.signal.savgol_filter.html)

## Sparse identification and selection

Fix theta_dot = omega and regress estimated acceleration on theta, theta cubed, sin(theta) and estimated omega. All columns and the acceleration target are divided by their training root mean squares. Apply sequential thresholded least squares with a dimensionless ridge penalty of 1e-8 during support selection, followed by an unregularized refit on the retained columns. This small ridge penalty stabilizes the thresholding steps in a correlated library. Convert coefficients back to their original units. A term is selected if its final coefficient is nonzero. [SINDy paper and STLSQ algorithm](https://arxiv.org/abs/1509.03580)

The threshold grid is 0, 0.005, 0.02, 0.05, 0.1, 0.25, 0.5 and 1.0 on the scaled coefficients. For every repetition, training condition and preprocessing method, choose the candidate with the lowest mean 10-second angle RMSE on the two validation trajectories. Score against the raw noisy validation angles. Within 1e-10 rad of the best score, prefer fewer terms, then the smaller score, then configuration order. A model must complete both validation rollouts to enter selection.

Use DOP853 and the Phase 1 solver settings for every rollout. End a rollout at either |theta| = 2 pi rad or |omega| = 100 rad/s and record a state-limit failure. Record incomplete numerical solves separately. The comparison reports completion alongside error. The selection file is saved and hashed before the test reference trajectories are generated.

## Outcomes

For each selected model, save all four coefficients, support, training acceleration RMSE and validation rollout RMSE. Report the test angle RMSE, completion status, period relative error when two descending crossings are available, and the interpolation or extrapolation label by initial amplitude. Report the sine coefficient relative error conditional on that term being present, and the corresponding error conditional on exact recovery of the sine-only support.

Summarize across independent seeds using the mean and sample standard deviation. For the main error summary a repetition must complete all three test rollouts. Per-angle summaries use completed trajectories at that angle and include their denominators. Exact support frequency uses all intended repetitions and includes a 95% Wilson interval for noisy conditions. Derivative accuracy is measured on validation trajectories after model selection using the reference derivatives. Training feature correlations and the scaled design condition number describe collinearity.

Training B increases both initial-angle coverage and the number of observed trajectories. The validation angles are in the small-angle regime. Report these features when interpreting extrapolation. The library supplies the sine term before fitting, so exact recovery measures selection within that library.
