"""Regenerate figures from saved experiment data."""

import argparse
from pathlib import Path

from pendulum_research.visualization import generate_figures

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--results", type=Path, default=root / "results/baseline")
parser.add_argument("--figures", type=Path, default=root / "figures/baseline")
args = parser.parse_args()
results_dir, figure_dir = args.results.resolve(), args.figures.resolve()
if not results_dir.is_relative_to(root) or not figure_dir.is_relative_to(root):
    parser.error("All experiment data and figures must remain within the project.")
generate_figures(results_dir, figure_dir)
