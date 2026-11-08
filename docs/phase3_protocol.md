# Phase 3 protocol

## Formal statements

Use Lean 4.24.0 and Mathlib revision `f897ebcf72cd16f89ab4577d0c826cd14afaafc7` in the project filesystem sandbox. The official Lean archive is checked against its release SHA-256. The Lake manifest pins all package revisions. [Lean release](https://github.com/leanprover/lean4/releases/tag/v4.24.0) · [Mathlib release](https://github.com/leanprover-community/mathlib4/releases/tag/v4.24.0)

Let angle and angular velocity be real-valued functions of time. The energy per unit moment of inertia is

```text
E_phys(theta, omega) = omega^2 / 2 + k * (1 - cos(theta))
```

At a time with theta_dot = omega and omega_dot = f(theta, omega), the derivative of E_phys is omega times the sum of f and k sin(theta). This is a HasDerivAt statement. For the true pendulum the two acceleration terms cancel. For interval conservation, require continuity of angle and velocity on the closed interval and the two derivative hypotheses at every interior time. The mean value theorem then gives equality between any two times in the interval. [Mathlib mean value theorem at the pinned version](https://github.com/leanprover-community/mathlib4/blob/f897ebcf72cd16f89ab4577d0c826cd14afaafc7/Mathlib/Analysis/Calculus/Deriv/MeanValue.lean)

The linear model has its own quadratic-potential energy. The cubic model has a quartic-potential energy. The SINDy family uses coefficients c1, c2, c3 and c4 for theta, theta cubed, sine and velocity. Its reference energy rate and its fitted-model energy rate are

```text
d E_phys / dt = omega * (c1 theta + c2 theta^3 + (c3 + k) sin(theta) + c4 omega)
d E_fit  / dt = c4 omega^2
```

The all-state zero-rate theorem characterizes the exact reference tuple (0, 0, -k, 0). The separate frozen-model theorem specializes the derivative identity to an index in the archived coefficient table at k = 981/100. The Lean exporter encodes each stored decimal exactly as a rational real literal.

## Numerical comparison

Use the frozen Phase 2 selected equations, test rollout statuses and archived state samples. The normalized drift for each completed trajectory is the largest sampled absolute change in E_phys divided by its positive initial E_phys. Use the same physical k = 9.81 for all models. Evaluate the proved rate formula at every saved nominal sample. Compute exact all-state coefficient matches using the archived decimal values.

Reintegrate all test cases with the same initial conditions and guards, using DOP853 with relative tolerance 1e-13, absolute tolerance 1e-15 and maximum internal step 0.05 s. Save tightened energy on a 0.01 s grid. Compare its drift on the shared 0.02 s samples with the nominal drift. The numerical agreement diagnostic is an absolute allowance of 1e-8 plus 1e-5 times the larger of the two drift values. Compare the tightened 0.01 s and 0.02 s sampled maxima separately to expose sampling effects.

A state-limit stop is retained as an incomplete rollout, with its drift field blank for the affected solver run. The main group summary averages across the three angles only for repetitions with all three nominal rollouts complete, then reports seed-level descriptive statistics and the completion count. Per-angle summaries use completed trajectories at that angle. The baseline illustration uses the pre-existing Training A predictions at 90 degrees.

The proofs describe exact differentiable solutions under their stated hypotheses. The experiment evaluates a finite sample of a numerical solution. A small sampled drift characterizes the evaluated trajectory, while the all-state theorem has a separate exact coefficient condition.
