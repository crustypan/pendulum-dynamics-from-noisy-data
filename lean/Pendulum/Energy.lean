import Mathlib.Analysis.Calculus.Deriv.MeanValue
import Mathlib.Analysis.Calculus.Deriv.Pow
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Deriv
import Mathlib.Tactic.Ring

/-! Exact energy identities for differentiable pendulum trajectories. -/

open Set

namespace Pendulum

noncomputable section

/-- Physical energy per unit moment of inertia for the reference pendulum. -/
def physicalEnergy (k angle speed : ℝ) : ℝ :=
  speed ^ 2 / 2 + k * (1 - Real.cos angle)

/-- Energy of the fitted linear oscillator. -/
def linearEnergy (a angle speed : ℝ) : ℝ :=
  speed ^ 2 / 2 + a * (angle ^ 2 / 2)

/-- Energy of the fitted cubic oscillator. -/
def polynomialEnergy (a b angle speed : ℝ) : ℝ :=
  speed ^ 2 / 2 + a * (angle ^ 2 / 2) + b * (angle ^ 4 / 4)

private theorem halfSquare_hasDerivAt {x : ℝ → ℝ} {v t : ℝ}
    (hx : HasDerivAt x v t) :
    HasDerivAt (fun s => (x s) ^ 2 / 2) (x t * v) t := by
  convert (hx.fun_pow 2).div_const 2 using 1
  norm_num
  ring

/-- The reference physical energy rate along a solution of any candidate acceleration. -/
theorem physicalEnergy_hasDerivAt (k : ℝ) (f : ℝ → ℝ → ℝ)
    {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (f (θ t) (ω t)) t) :
    HasDerivAt (fun s => physicalEnergy k (θ s) (ω s))
      (ω t * (f (θ t) (ω t) + k * Real.sin (θ t))) t := by
  have hcos : HasDerivAt (fun s => Real.cos (θ s)) (-Real.sin (θ t) * ω t) t :=
    (Real.hasDerivAt_cos (θ t)).comp t hθ
  have hpot := ((hasDerivAt_const t (1 : ℝ)).sub hcos).const_mul k
  convert (halfSquare_hasDerivAt hω).add hpot using 1
  ring

/-- The physical energy rate of a fitted linear oscillator. -/
theorem linear_physicalEnergy_hasDerivAt (k a : ℝ) {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (-a * θ t) t) :
    HasDerivAt (fun s => physicalEnergy k (θ s) (ω s))
      (ω t * (k * Real.sin (θ t) - a * θ t)) t := by
  convert physicalEnergy_hasDerivAt k (fun x _ => -a * x) hθ hω using 1
  ring

/-- The physical energy rate of a fitted sine-only oscillator. -/
theorem sinusoidal_physicalEnergy_hasDerivAt (k a : ℝ) {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (-a * Real.sin (θ t)) t) :
    HasDerivAt (fun s => physicalEnergy k (θ s) (ω s))
      ((k - a) * ω t * Real.sin (θ t)) t := by
  convert physicalEnergy_hasDerivAt k (fun x _ => -a * Real.sin x) hθ hω using 1
  ring

/-- The ideal nonlinear pendulum has zero physical energy derivative. -/
theorem truePendulum_physicalEnergy_hasDerivAt_zero (k : ℝ) {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (-k * Real.sin (θ t)) t) :
    HasDerivAt (fun s => physicalEnergy k (θ s) (ω s)) 0 t := by
  simpa using sinusoidal_physicalEnergy_hasDerivAt k k hθ hω

private theorem eq_on_Icc_of_hasDerivAt_zero {E : ℝ → ℝ} {lo hi s t : ℝ}
    (hc : ContinuousOn E (Icc lo hi))
    (hd : ∀ x ∈ Ioo lo hi, HasDerivAt E 0 x)
    (hs : s ∈ Icc lo hi) (ht : t ∈ Icc lo hi) : E s = E t := by
  have ordered (x y : ℝ) (hx : x ∈ Icc lo hi) (hy : y ∈ Icc lo hi)
      (hxy : x < y) : E x = E y := by
    obtain ⟨_, _, hslope⟩ := exists_hasDerivAt_eq_slope E (fun _ => 0) hxy
      (hc.mono (fun _ hz => ⟨le_trans hx.1 hz.1, le_trans hz.2 hy.2⟩))
      (fun z hz => hd z ⟨lt_of_le_of_lt hx.1 hz.1, lt_of_lt_of_le hz.2 hy.2⟩)
    have hdiff : E y - E x = 0 := by
      have h := (div_eq_iff (sub_ne_zero.mpr (ne_of_gt hxy))).mp hslope.symm
      simpa using h
    exact (sub_eq_zero.mp hdiff).symm
  rcases lt_trichotomy s t with h | h | h
  · exact ordered s t hs ht h
  · rw [h]
  · exact (ordered t s ht hs h).symm

/-- Physical energy is constant on a closed interval for continuous ideal trajectories
with the stated dynamics at every interior time. -/
theorem truePendulum_physicalEnergy_eq_on_Icc (k : ℝ) {θ ω : ℝ → ℝ} {lo hi s t : ℝ}
    (hcθ : ContinuousOn θ (Icc lo hi)) (hcω : ContinuousOn ω (Icc lo hi))
    (hθ : ∀ x ∈ Ioo lo hi, HasDerivAt θ (ω x) x)
    (hω : ∀ x ∈ Ioo lo hi, HasDerivAt ω (-k * Real.sin (θ x)) x)
    (hs : s ∈ Icc lo hi) (ht : t ∈ Icc lo hi) :
    physicalEnergy k (θ s) (ω s) = physicalEnergy k (θ t) (ω t) := by
  have hc : ContinuousOn (fun x => physicalEnergy k (θ x) (ω x)) (Icc lo hi) := by
    unfold physicalEnergy
    exact ((hcω.pow 2).div_const 2).add
      (continuousOn_const.mul (continuousOn_const.sub (Real.continuous_cos.comp_continuousOn hcθ)))
  exact eq_on_Icc_of_hasDerivAt_zero hc
    (fun x hx => truePendulum_physicalEnergy_hasDerivAt_zero k (hθ x hx) (hω x hx)) hs ht

/-- A linear trajectory conserves the energy of its own oscillator. -/
theorem linearEnergy_hasDerivAt_zero (a : ℝ) {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (-a * θ t) t) :
    HasDerivAt (fun s => linearEnergy a (θ s) (ω s)) 0 t := by
  convert (halfSquare_hasDerivAt hω).add ((halfSquare_hasDerivAt hθ).const_mul a)
    using 1
  ring

/-- The fitted linear oscillator energy is constant throughout the stated interval. -/
theorem linearEnergy_eq_on_Icc (a : ℝ) {θ ω : ℝ → ℝ} {lo hi s t : ℝ}
    (hcθ : ContinuousOn θ (Icc lo hi)) (hcω : ContinuousOn ω (Icc lo hi))
    (hθ : ∀ x ∈ Ioo lo hi, HasDerivAt θ (ω x) x)
    (hω : ∀ x ∈ Ioo lo hi, HasDerivAt ω (-a * θ x) x)
    (hs : s ∈ Icc lo hi) (ht : t ∈ Icc lo hi) :
    linearEnergy a (θ s) (ω s) = linearEnergy a (θ t) (ω t) := by
  have hc : ContinuousOn (fun x => linearEnergy a (θ x) (ω x)) (Icc lo hi) := by
    unfold linearEnergy
    exact ((hcω.pow 2).div_const 2).add
      (continuousOn_const.mul ((hcθ.pow 2).div_const 2))
  exact eq_on_Icc_of_hasDerivAt_zero hc
    (fun x hx => linearEnergy_hasDerivAt_zero a (hθ x hx) (hω x hx)) hs ht

/-- A cubic trajectory has zero derivative of its own quartic-potential energy. -/
theorem polynomialEnergy_hasDerivAt_zero (a b : ℝ) {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (-a * θ t - b * (θ t) ^ 3) t) :
    HasDerivAt (fun s => polynomialEnergy a b (θ s) (ω s)) 0 t := by
  have hq := ((hθ.fun_pow 4).div_const 4).const_mul b
  convert ((halfSquare_hasDerivAt hω).add ((halfSquare_hasDerivAt hθ).const_mul a)).add hq
    using 1
  norm_num
  ring

/-- Coefficients in the Phase 2 library theta, theta cubed, sine and velocity. -/
structure SindyCoefficients where
  linear : ℝ
  cubic : ℝ
  sine : ℝ
  velocity : ℝ

/-- Acceleration represented by a selected SINDy coefficient record. -/
def sindyAcceleration (c : SindyCoefficients) (angle speed : ℝ) : ℝ :=
  c.linear * angle + c.cubic * angle ^ 3 + c.sine * Real.sin angle + c.velocity * speed

/-- The reference physical energy rate expressed directly in the selected coefficients. -/
def sindyPhysicalRate (k : ℝ) (c : SindyCoefficients) (angle speed : ℝ) : ℝ :=
  speed * (c.linear * angle + c.cubic * angle ^ 3 +
    (c.sine + k) * Real.sin angle + c.velocity * speed)

/-- Every solution of the SINDy family has the stated physical energy rate. -/
theorem sindy_physicalEnergy_hasDerivAt (k : ℝ) (c : SindyCoefficients)
    {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (sindyAcceleration c (θ t) (ω t)) t) :
    HasDerivAt (fun s => physicalEnergy k (θ s) (ω s))
      (sindyPhysicalRate k c (θ t) (ω t)) t := by
  convert physicalEnergy_hasDerivAt k (sindyAcceleration c) hθ hω using 1
  unfold sindyAcceleration sindyPhysicalRate
  ring

/-- The energy formed from the position-dependent terms of the fitted SINDy field. -/
def sindyModelEnergy (c : SindyCoefficients) (angle speed : ℝ) : ℝ :=
  speed ^ 2 / 2 - c.linear * (angle ^ 2 / 2) - c.cubic * (angle ^ 4 / 4) +
    c.sine * (Real.cos angle - 1)

/-- The fitted SINDy energy rate is determined by its velocity coefficient. -/
theorem sindy_modelEnergy_hasDerivAt (c : SindyCoefficients)
    {θ ω : ℝ → ℝ} {t : ℝ}
    (hθ : HasDerivAt θ (ω t) t) (hω : HasDerivAt ω (sindyAcceleration c (θ t) (ω t)) t) :
    HasDerivAt (fun s => sindyModelEnergy c (θ s) (ω s)) (c.velocity * (ω t) ^ 2) t := by
  have hcos : HasDerivAt (fun s => Real.cos (θ s)) (-Real.sin (θ t) * ω t) t :=
    (Real.hasDerivAt_cos (θ t)).comp t hθ
  have hsin := (hcos.sub (hasDerivAt_const t (1 : ℝ))).const_mul c.sine
  have hlin := (halfSquare_hasDerivAt hθ).const_mul c.linear
  have hcub := ((hθ.fun_pow 4).div_const 4).const_mul c.cubic
  convert (((halfSquare_hasDerivAt hω).sub hlin).sub hcub).add hsin using 1
  unfold sindyAcceleration
  norm_num
  ring

/-- The physical energy rate vanishes at every real state exactly for the reference
coefficient tuple. The conclusion concerns the entire candidate vector field. -/
theorem sindyPhysicalRate_zero_everywhere_iff (k : ℝ) (c : SindyCoefficients) :
    (∀ angle speed : ℝ, sindyPhysicalRate k c angle speed = 0) ↔
      c.linear = 0 ∧ c.cubic = 0 ∧ c.sine = -k ∧ c.velocity = 0 := by
  constructor
  · intro h
    have hvel : c.velocity = 0 := by simpa [sindyPhysicalRate] using h 0 1
    have hpi := h Real.pi 1
    simp only [sindyPhysicalRate, Real.sin_pi, hvel, mul_zero, zero_mul, add_zero, one_mul] at hpi
    have h2pi := h (2 * Real.pi) 1
    simp only [sindyPhysicalRate, Real.sin_two_pi, hvel, mul_zero, zero_mul, add_zero, one_mul] at h2pi
    have hscaled : (6 : ℝ) * (c.cubic * Real.pi ^ 3) = 0 := calc
      _ = (c.linear * (2 * Real.pi) + c.cubic * (2 * Real.pi) ^ 3) -
          2 * (c.linear * Real.pi + c.cubic * Real.pi ^ 3) := by ring
      _ = 0 := by simp [h2pi, hpi]
    have hprod : c.cubic * Real.pi ^ 3 = 0 := (mul_eq_zero.mp hscaled).resolve_left (by norm_num)
    have hπ : Real.pi ≠ 0 := ne_of_gt Real.pi_pos
    have hcub : c.cubic = 0 := (mul_eq_zero.mp hprod).resolve_right (pow_ne_zero 3 hπ)
    have hlinprod : c.linear * Real.pi = 0 := by simpa [hcub] using hpi
    have hlin : c.linear = 0 := (mul_eq_zero.mp hlinprod).resolve_right hπ
    have hsin := h (Real.pi / 2) 1
    simp only [sindyPhysicalRate, Real.sin_pi_div_two, hlin, hcub, hvel,
      zero_mul, zero_add, mul_one, add_zero, one_mul] at hsin
    have hs : c.sine = -k := calc
      c.sine = (c.sine + k) - k := by ring
      _ = -k := by rw [hsin, zero_sub]
    exact ⟨hlin, hcub, hs, hvel⟩
  · rintro ⟨hlin, hcub, hsin, hvel⟩ angle speed
    simp [sindyPhysicalRate, hlin, hcub, hsin, hvel]

end
end Pendulum
