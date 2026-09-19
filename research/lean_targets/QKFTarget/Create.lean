import QKFTarget.Ceiling

/-! Mathematical caller invariants used by the source-bound Graal create proof.

This module does not parse Java. It removes several caller-level rules from the
Python mathematical trust base: signed order inside a fixed sign bucket,
common-prefix refinement from monotone observations, exact-extrema monotonicity,
exact emptiness, and the final fixed-point confirmation once a state is known
normalized. The source-to-premise bridge remains external and versioned.
-/
namespace QKFTarget.Create

/-- Signed interpretation with an explicit sign threshold and modulus. -/
def signedWord (half modulus z : Nat) : Int :=
  if z < half then Int.ofNat z else Int.ofNat z - Int.ofNat modulus

def SameSignBucket (half a b : Nat) : Prop :=
  (a < half ∧ b < half) ∨ (half ≤ a ∧ half ≤ b)

theorem signed_order_low (half modulus a b : Nat)
    (ha : a < half) (hb : b < half) :
    signedWord half modulus a ≤ signedWord half modulus b ↔ a ≤ b := by
  simpa only [signedWord, if_pos ha, if_pos hb, Int.ofNat_le]

theorem signed_order_high (half modulus a b : Nat)
    (ha : half ≤ a) (hb : half ≤ b) :
    signedWord half modulus a ≤ signedWord half modulus b ↔ a ≤ b := by
  have hna : ¬ a < half := Nat.not_lt.mpr ha
  have hnb : ¬ b < half := Nat.not_lt.mpr hb
  simpa only [signedWord, if_neg hna, if_neg hnb, sub_le_sub_iff_right, Int.ofNat_le]

/-- Once the sign bucket is fixed, signed Java order and payload order agree. -/
theorem signed_order_same_bucket (half modulus a b : Nat)
    (same : SameSignBucket half a b) :
    signedWord half modulus a ≤ signedWord half modulus b ↔ a ≤ b := by
  rcases same with low | high
  · exact signed_order_low half modulus a b low.1 low.2
  · exact signed_order_high half modulus a b high.1 high.2

/-- A consumer observation used as a common-prefix key only needs monotonicity. -/
def MonotoneKey (key : Nat → Nat) : Prop :=
  ∀ ⦃a b⦄, a ≤ b → key a ≤ key b

theorem interval_key_eq (key : Nat → Nat) (mono : MonotoneKey key)
    (lo hi z : Nat) (hl : lo ≤ z) (hu : z ≤ hi)
    (same : key lo = key hi) : key z = key lo := by
  have lower : key lo ≤ key z := mono hl
  have upper : key z ≤ key hi := mono hu
  omega

def Refined (L : Nat → Prop) (key : Nat → Nat) (k z : Nat) : Prop :=
  L z ∧ key z = k

/-- Adding a common-prefix fact true throughout exact bounds cannot change the carrier. -/
theorem common_prefix_refinement_preserves (L : Nat → Prop) (key : Nat → Nat)
    (mono : MonotoneKey key) (lo hi : Nat)
    (bounds : ∀ z, L z → lo ≤ z ∧ z ≤ hi)
    (same : key lo = key hi) (z : Nat) :
    Refined L key (key lo) z ↔ L z := by
  constructor
  · exact fun h => h.1
  · intro hz
    exact ⟨hz, interval_key_eq key mono lo hi z (bounds z hz).1 (bounds z hz).2 same⟩

structure ExactExtrema (L : Nat → Prop) (lo hi : Nat) : Prop where
  lower_legal : L lo
  upper_legal : L hi
  bounds : ∀ z, L z → lo ≤ z ∧ z ≤ hi

def Covers (L : Nat → Prop) (lo hi : Nat) : Prop :=
  ∀ z, L z → lo ≤ z ∧ z ≤ hi

/-- Exact extrema can only tighten any already sound caller interval. -/
theorem exact_extrema_tighten (L : Nat → Prop) (oldLo oldHi lo hi : Nat)
    (old : Covers L oldLo oldHi) (exact : ExactExtrema L lo hi) :
    oldLo ≤ lo ∧ hi ≤ oldHi := by
  exact ⟨(old lo exact.lower_legal).1, (old hi exact.upper_legal).2⟩

/-- Empty is an exact semantic outcome, not a numeric sentinel. -/
theorem exact_empty_iff_no_legal (L : Nat → Prop) :
    (∀ z, ¬ L z) ↔ ¬ ∃ z, L z := by
  constructor
  · intro h hex
    obtain ⟨z, hz⟩ := hex
    exact h z hz
  · intro h z hz
    exact h ⟨z, hz⟩

/-- A later legal maximum witnesses that a nonwrapping successor exists. -/
theorem greater_witness_from_maximum (L : Nat → Prop)
    (maximum bound floor : Nat) (maximum_legal : L maximum)
    (gap : floor < bound) (bound_below : bound ≤ maximum) :
    ∃ z, L z ∧ floor < z := by
  exact ⟨maximum, maximum_legal, Nat.lt_of_lt_of_le gap bound_below⟩

/-- Generic final-confirmation lemma for the source's third pass.

The substantive obligation is that two changing passes establish Normal.
Once normalized states are fixed by step, the third pass is provably only a
confirmation. This theorem keeps that remaining source/export obligation explicit.
-/
theorem third_pass_confirmation {S : Type} (step : S → S) (Normal : S → Prop)
    (normal_after_two : ∀ s, Normal (step (step s)))
    (fixed_when_normal : ∀ s, Normal s → step s = s) (s : S) :
    step (step (step s)) = step (step s) := by
  exact fixed_when_normal (step (step s)) (normal_after_two s)

/-- Existing exact-ceiling composition consumes the caller-derived floor and successor contracts. -/
theorem exact_ceiling_from_caller_contracts (L : Nat → Prop)
    (minimum maximum bound : Nat)
    (minimum_legal : L minimum) (maximum_legal : L maximum)
    (limits : ∀ z, L z → minimum ≤ z ∧ z ≤ maximum)
    (floor next : Nat → Nat)
    (floor_ok : ∀ b, minimum ≤ b → b ≤ maximum →
      Ceiling.FloorContract L b (floor b))
    (next_ok : ∀ g, L g → Ceiling.SuccessorContract L minimum g (next g)) :
    Ceiling.ExactCeiling L bound
      (Ceiling.compose minimum maximum bound floor next) := by
  exact Ceiling.compose_correct L minimum maximum minimum_legal maximum_legal
    limits floor next floor_ok next_ok bound

end QKFTarget.Create
