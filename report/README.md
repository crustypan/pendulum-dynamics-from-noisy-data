# Research report and application highlight

| Deliverable | PDF | Editable source |
| --- | --- | --- |
| Research report, 6 pages | [Download](pdf/research_report.pdf) | [Markdown](research_report.md) |
| Research Highlight, 1 page | [Download](pdf/research_highlight.pdf) | [Markdown](research_highlight.md) |

The report follows the study from clean baselines through noisy identification, guard replay, Lean energy theorems and numerical energy drift. The highlight is a standalone summary for graduate applications. Both documents describe the same completed experiments.

## Figure and evidence index

| Report section | Full-size figures | Data and audit |
| --- | --- | --- |
| Clean baseline | [Trajectories](../figures/baseline/trajectory_comparison.png), [test RMSE](../figures/baseline/test_rmse.png) | [Coefficients](../results/baseline/models.json), [metrics](../results/baseline/metrics.csv) |
| Noisy identification | [Noise robustness](../figures/noise_sindy/noise_robustness.png), [derivative estimates](../figures/noise_sindy/derivative_estimation.png) | [Frozen models](../results/noise_sindy/selected_models.csv), [seed summaries](../results/noise_sindy/summary.csv) |
| Failure diagnosis | [Release acceleration and guard stops](../figures/failure_diagnostics/failure_mechanisms.png) | [Methods and replay records](../docs/phase4_failure_analysis.md) |
| Formal and numerical energy results | [Baseline energy](../figures/energy_drift/baseline_conservation.png), [SINDy drift](../figures/energy_drift/physical_energy_drift.png) | [Lean verification](../results/lean_verification/verification.json), [trajectory drift](../results/energy_drift/trajectory_energy.csv) |

## Build the PDFs

Use the [locked Python environment](../README.md#reproduce-the-results) and the Linux Lato and DejaVu font files. ReportLab and the PDF reader are pinned separately from the experimental environment and installed in the ignored project-local tools directory.

```bash
python3 -B scripts/run_isolated.py --network -- .venv/bin/python -m pip install --disable-pip-version-check --only-binary=:all: --no-deps --target .tools/report-packages -r requirements-report-lock.txt
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/build_phase4_reports.py --output .tmp/pdfs/reproduction
python3 -B scripts/run_isolated.py -- .venv/bin/python scripts/verify_phase4.py
```

The [build receipt](pdf/build_receipt.json) records page counts and hashes of the Markdown, figures, build code and PDFs. The [Phase 4 checks](../results/phase4_checks) record the final verification. Figures are embedded in the PDFs and linked at full size in the Markdown. Keep both versions when preparing the repository.
