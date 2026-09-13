import QKF.Checked
import Lean.Elab.Tactic.Omega

namespace QKF

def digit (b : Bool) : Nat := if b then 1 else 0
def cmpNat (a b : Nat) : Order3 := if a < b then .lt else if a = b then .eq else .gt
def cmpInt (a b : Int) : Order3 := if a < b then .lt else if a = b then .eq else .gt

theorem cmpNat_high {a b base : Nat} (ha : a < base) (hb : b < base)
    (x y : Bool) :
    cmpNat (a + digit x * base) (b + digit y * base) = prepend x y (cmpNat a b) := by
  cases x <;> cases y
  · simp [digit, prepend, bitCmp]
  · have h : a < b + base := by omega
    simp [digit, prepend, bitCmp, cmpNat, h]
  · have h₁ : ¬ a + base < b := by omega
    have h₂ : a + base ≠ b := by omega
    simp [digit, prepend, bitCmp, cmpNat, h₁, h₂]
  · simp [digit, prepend, bitCmp, cmpNat]

theorem digit_bound {a base : Nat} (ha : a < base) (b : Bool) :
    a + digit b * base < base * 2 := by
  cases b <;> simp [digit] <;> omega

structure WordState where
  width : Nat
  g : Nat
  x : Nat
  t : Nat
  carry : Bool
  trace : List (Column × Bool)
  deriving Repr

def wordStart : WordState := ⟨0, 0, 0, 0, true, []⟩

/- Low bits are read first. Each new bit has weight 2^width. -/
def wordStep (s : WordState) (c : Column) : WordState :=
  let action := stepFromRows Data.rows c s.carry
  ⟨s.width + 1, s.g + digit (inputBit c) * 2 ^ s.width,
    s.x + digit (candidateBit c) * 2 ^ s.width,
    s.t + digit action.1 * 2 ^ s.width, action.2,
    s.trace ++ [(c, action.1)]⟩

theorem word_width (columns : List Column) (s : WordState) :
    (run wordStep s columns).width = s.width + columns.length := by
  induction columns generalizing s with
  | nil => simp [run]
  | cons c rest ih =>
    rw [run, ih]
    simp [wordStep, Nat.add_assoc, Nat.add_comm]

structure Agrees (q : Observation) (s : WordState) : Prop where
  carry : q.carry = s.carry
  gx : q.gx = cmpNat s.g s.x
  tx : q.tx = cmpNat s.t s.x
  gt : q.gt = cmpNat s.g s.t
  gBound : s.g < 2 ^ s.width
  xBound : s.x < 2 ^ s.width
  tBound : s.t < 2 ^ s.width

theorem start_agrees : Agrees start wordStart := by
  constructor <;> decide

theorem step_agrees (q : Observation) (s : WordState) (h : Agrees q s) (c : Column) :
    Agrees (transition Data.rows q c) (wordStep s c) := by
  constructor
  · change (stepFromRows Data.rows c q.carry).2 = (stepFromRows Data.rows c s.carry).2
    rw [h.carry]
  · change prepend (inputBit c) (candidateBit c) q.gx = _
    rw [h.gx]
    exact (cmpNat_high h.gBound h.xBound _ _).symm
  · change prepend (stepFromRows Data.rows c q.carry).1 (candidateBit c) q.tx = _
    rw [h.carry, h.tx]
    exact (cmpNat_high h.tBound h.xBound _ _).symm
  · change prepend (inputBit c) (stepFromRows Data.rows c q.carry).1 q.gt = _
    rw [h.carry, h.gt]
    exact (cmpNat_high h.gBound h.tBound _ _).symm
  · change s.g + digit (inputBit c) * 2 ^ s.width < 2 ^ (s.width + 1)
    rw [Nat.pow_succ]
    exact digit_bound h.gBound _
  · change s.x + digit (candidateBit c) * 2 ^ s.width < 2 ^ (s.width + 1)
    rw [Nat.pow_succ]
    exact digit_bound h.xBound _
  · change s.t + digit (stepFromRows Data.rows c s.carry).1 * 2 ^ s.width < 2 ^ (s.width + 1)
    rw [Nat.pow_succ]
    exact digit_bound h.tBound _

theorem word_agrees (xs : List Column) :
    Agrees (run (transition Data.rows) start xs) (run wordStep wordStart xs) :=
  run_relation (transition Data.rows) wordStep Agrees step_agrees start_agrees xs

def TraceAllowed (s : WordState) : Prop :=
  ∀ entry ∈ s.trace, allowed (mustBit entry.1) (mayBit entry.1) entry.2 = true

theorem word_trace_allowed (xs : List Column) : TraceAllowed (run wordStep wordStart xs) := by
  have step : ∀ s, TraceAllowed s → ∀ c, TraceAllowed (wordStep s c) := by
    intro s h c entry hm
    change entry ∈ s.trace ++ [(c, (stepFromRows Data.rows c s.carry).1)] at hm
    simp only [List.mem_append, List.mem_singleton] at hm
    rcases hm with old | fresh
    · exact h entry old
    · subst entry
      rw [glued_cell_correct]
      exact native_cell_membership c s.carry
  have general : ∀ (ys : List Column) (s : WordState), TraceAllowed s → TraceAllowed (run wordStep s ys) := by
    intro ys
    induction ys with
    | nil => intro s h; exact h
    | cons c rest ih => intro s h; exact ih (wordStep s c) (step s h c)
  apply general xs wordStart
  intro entry hm
  simp [wordStart] at hm

def signed (value base : Nat) (negative : Bool) : Int :=
  if negative then (value : Int) - (base : Int) else (value : Int)

theorem signed_compare {a b base : Nat} (ha : a < base) (hb : b < base)
    (sa sb : Bool) :
    cmpInt (signed a base sa) (signed b base sb) = prepend (!sa) (!sb) (cmpNat a b) := by
  cases sa <;> cases sb
  · simp [signed, cmpInt, cmpNat, prepend, bitCmp, Int.ofNat_inj]
  · have h₁ : ¬ (a : Int) < (b : Int) - (base : Int) := by omega
    have h₂ : (a : Int) ≠ (b : Int) - (base : Int) := by omega
    simp [signed, cmpInt, prepend, bitCmp, h₁, h₂]
  · have h : (a : Int) - (base : Int) < (b : Int) := by omega
    simp [signed, cmpInt, prepend, bitCmp, h]
  · simp [signed, cmpInt, cmpNat, prepend, bitCmp, Int.ofNat_inj]

theorem cmpInt_lt_iff (a b : Int) : cmpInt a b = .lt ↔ a < b := by
  unfold cmpInt
  split <;> simp_all
  split <;> simp_all

theorem cmpInt_not_gt_iff (a b : Int) : cmpInt a b ≠ .gt ↔ a ≤ b := by
  unfold cmpInt
  split
  · simp_all; omega
  · split <;> simp_all <;> omega

/- Main semantic result. A Column encodes exactly one of the six legal
(must,may,input,candidate) bit combinations. The final sign is handled
separately with its reversed signed order. -/
theorem mask_successor_all_widths (columns : List Column) (mask : SignMask) (xs : Bool)
    (hx : allowed (signMust mask) (signMay mask) xs = true)
    (hgreater :
      signed (run wordStep wordStart columns).g (2 ^ (run wordStep wordStart columns).width) (signMay mask) <
      signed (run wordStep wordStart columns).x (2 ^ (run wordStep wordStart columns).width) xs) :
    let s := run wordStep wordStart columns
    let ts := bxor (signMay mask) s.carry
    !(s.carry && !signMay mask) = true ∧
    allowed (signMust mask) (signMay mask) ts = true ∧
    TraceAllowed s ∧
    signed s.g (2 ^ s.width) (signMay mask) < signed s.t (2 ^ s.width) ts ∧
    signed s.t (2 ^ s.width) ts ≤ signed s.x (2 ^ s.width) xs := by
  let q := run (transition Data.rows) start columns
  let s := run wordStep wordStart columns
  have agrees : Agrees q s := word_agrees columns
  have hgx : prepend (!(signMay mask)) (!xs) q.gx = .lt := by
    rw [agrees.gx, ← signed_compare agrees.gBound agrees.xBound]
    exact (cmpInt_lt_iff _ _).mpr hgreater
  have result := observation_all_lengths columns mask xs hx hgx
  change !(q.carry && !signMay mask) = true ∧
    allowed (signMust mask) (signMay mask) (bxor (signMay mask) q.carry) = true ∧
    prepend (!(signMay mask)) (!(bxor (signMay mask) q.carry)) q.gt = .lt ∧
    prepend (!(bxor (signMay mask) q.carry)) (!xs) q.tx ≠ .gt at result
  rw [agrees.carry] at result
  refine ⟨result.1, result.2.1, word_trace_allowed columns, ?_, ?_⟩
  · apply (cmpInt_lt_iff _ _).mp
    rw [signed_compare agrees.gBound agrees.tBound, ← agrees.gt]
    exact result.2.2.1
  · apply (cmpInt_not_gt_iff _ _).mp
    rw [signed_compare agrees.tBound agrees.xBound, ← agrees.tx]
    exact result.2.2.2

end QKF
