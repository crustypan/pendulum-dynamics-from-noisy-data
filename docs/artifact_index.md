# Data and proof guide

Use the [report index](../report/README.md) for the figures and [the README](../README.md) for reproducibility commands. Angles are in radians internally. Fields with explicit unit suffixes use the indicated unit.

| Archive | Key files |
| --- | --- |
| [Phase 1 baselines](../results/baseline) | `models.json` gives the six fitted equations; `metrics.csv` contains angle RMSE, period and parameter errors; `predictions.csv` and `reference.csv` are the sampled trajectories; `reference_checks.csv` records the energy and period benchmarks. |
| [Phase 2 SINDy](../results/noise_sindy) | `selected_models.csv` is the frozen coefficient table; `selection_frozen.json` records its digest; `validation_grid.csv.gz` preserves candidate scores; `test_metrics.csv` and `test_predictions.npz` join by `prediction_index`. `observations.npz`, `reference.npz` and `trials.csv` retain the synthetic samples and seeds. `summary.csv`, `support_frequencies.csv`, `derivative_metrics.csv`, `paired_comparisons.csv` and `test_summary_by_angle.csv` report the comparisons. |
| [Phase 3 physical energy](../results/energy_drift) | `model_energy.csv` preserves exact coefficient tests; `trajectory_energy.csv` and `energy_traces.npz` join by `prediction_index`. `group_energy.csv` and `angle_energy.csv` give aggregation counts and drift. `baseline_energy.csv` and `reference_energy.csv` provide reference comparisons. |
| [Lean verification](../results/lean_verification) | `verification.json` records versions, revisions, hashes and dependencies; `compile_transcript.log` and `build.log` record successful builds; `axioms.log` lists each audited theorem and its dependencies. |
| [Phase 4 failures](../results/failure_diagnostics) | `release_diagnostics.csv` covers all releases; `guard_replays.csv` records both terminal events for each of the 98 stops; `failure_by_condition.csv` aggregates stops; `failure_summary.json` records examples, settings and provenance. |
| [Verification](../results/phase4_checks) | `verification.json` audits the files and page counts; `lean_recheck.json`, `tests.log`, `rebuild.log` and `visual_review.json` record the checks completed for the report package. |

Each experiment keeps its configuration, completion status and artifact checksums in its archive. Incomplete trajectories retain their status and do not contribute a completed-run error or drift. The [Phase 2 results](phase2_results.md) and [Phase 3 results](phase3_results.md) explain the grouping, units and model assumptions in more detail.

The repository copy omits machine-specific test XML. The published checksums cover the retained research artifacts, and the final test summaries remain in the verification folders.
