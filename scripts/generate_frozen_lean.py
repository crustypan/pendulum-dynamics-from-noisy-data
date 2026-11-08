"""Export exact decimal Phase 2 coefficients as real rational literals for Lean."""

import argparse
import csv
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/noise_sindy"
TARGET = ROOT / "lean/Pendulum/FrozenModels.lean"
COLUMNS = ("c_theta", "c_theta_cubed", "c_sin_theta", "c_omega")


def literal(decimal: str) -> str:
    value = Fraction(Decimal(decimal))
    if value.denominator == 1:
        return f"({value.numerator} : ℝ)"
    return f"(({value.numerator} : ℝ) / {value.denominator})"


def generate() -> str:
    path = RESULTS / "selected_models.csv"
    expected = json.loads((RESULTS / "selection_frozen.json").read_text())["selected_models_sha256"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError("The Phase 2 frozen coefficient file differs from its recorded digest.")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = [row for row in csv.DictReader(stream) if row["fit_status"] == "selected"]
    ids = [row["model_id"] for row in rows]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for key in ids):
        raise ValueError("Model identifiers must be distinct and valid.")
    entries = [
        f'  ("{row["model_id"]}", ⟨' + ", ".join(literal(row[column]) for column in COLUMNS) + "⟩)"
        for row in rows
    ]
    header = (
        "import Pendulum.Energy\n\nnamespace Pendulum.FrozenModels\n\nnoncomputable section\n\n"
        f"/-- Exact decimal coefficients archived in Phase 2. SHA-256 {expected}. -/\n"
        "def coefficients : List (String × SindyCoefficients) := [\n"
    )
    footer = f"""\n]

/-- The number of frozen coefficient records included in this project. -/
theorem coefficient_count : coefficients.length = {len(rows)} := rfl

/-- Each frozen record specializes the physical energy rate theorem at k = 9.81. -/
theorem physicalEnergy_hasDerivAt_for_model (i : Fin coefficients.length)
    {{θ ω : ℝ → ℝ}} {{t : ℝ}}
    (hθ : HasDerivAt θ (ω t) t)
    (hω : HasDerivAt ω (sindyAcceleration (coefficients.get i).2 (θ t) (ω t)) t) :
    HasDerivAt (fun s => physicalEnergy (981 / 100) (θ s) (ω s))
      (sindyPhysicalRate (981 / 100) (coefficients.get i).2 (θ t) (ω t)) t :=
  sindy_physicalEnergy_hasDerivAt (981 / 100) (coefficients.get i).2 hθ hω

end
end Pendulum.FrozenModels
"""
    return header + ",\n".join(entries) + footer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = generate()
    if args.check:
        if TARGET.read_text(encoding="utf-8") != source:
            raise ValueError("The Lean coefficient table does not match the frozen input.")
    else:
        with TARGET.open("x", encoding="utf-8") as stream:
            stream.write(source)
    print("Frozen coefficient export matches Phase 2.")


if __name__ == "__main__":
    main()
