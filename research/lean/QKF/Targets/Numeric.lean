import QKF.Gluing
import Lean.Elab.Tactic.Omega

namespace QKF.Targets

inductive Order where
  | lt | eq | gt
  deriving DecidableEq, Repr, Inhabited

def digit (b : Bool) : Nat := if b then 1 else 0

def compare (a b : Nat) : Order :=
  if a < b then .lt else if a = b then .eq else .gt

def higher (x y : Bool) (old : Order) : Order :=
  if x == y then old else if x then .gt else .lt

theorem compare_higher {a b base : Nat} (ha : a < base) (hb : b < base)
    (x y : Bool) :
    compare (a + digit x * base) (b + digit y * base) = higher x y (compare a b) := by
  cases x <;> cases y
  · simp [digit, higher]
  · have h : a < b + base := by omega
    simp [digit, higher, compare, h]
  · have h₁ : ¬ a + base < b := by omega
    have h₂ : a + base ≠ b := by omega
    simp [digit, higher, compare, h₁, h₂]
  · simp [digit, higher, compare]

theorem compare_lt (a b : Nat) : compare a b = .lt ↔ a < b := by
  unfold compare
  split <;> simp_all
  split <;> simp_all

theorem compare_eq (a b : Nat) : compare a b = .eq ↔ a = b := by
  unfold compare
  split
  · simp_all; omega
  · split <;> simp_all

theorem compare_le (a b : Nat) : compare a b ≠ .gt ↔ a ≤ b := by
  unfold compare
  split
  · simp_all; omega
  · split <;> simp_all <;> omega

theorem extend_bound {a base : Nat} (ha : a < base) (b : Bool) :
    a + digit b * base < base * 2 := by
  cases b <;> simp [digit] <;> omega

theorem extend_eq {a b base : Nat} (ha : a < base) (hb : b < base)
    (x y : Bool) :
    (a + digit x * base = b + digit y * base) ↔ (a = b ∧ x = y) := by
  cases x <;> cases y <;> simp [digit] <;> omega

/- Low-to-high binary lists, with no fixed maximum width. -/
def value : List Bool → Nat
  | [] => 0
  | b :: bs => digit b + 2 * value bs

theorem value_bound (bs : List Bool) : value bs < 2 ^ bs.length := by
  induction bs with
  | nil => decide
  | cons b bs ih =>
    simp only [value, List.length_cons, Nat.pow_succ]
    cases b <;> simp only [digit, Bool.false_eq_true, if_false, if_true] <;> omega

theorem value_snoc (bs : List Bool) (b : Bool) :
    value (bs ++ [b]) = value bs + digit b * 2 ^ bs.length := by
  induction bs with
  | nil => simp [value]
  | cons a bs ih =>
    simp only [List.cons_append, value, List.length_cons, ih, Nat.pow_succ]
    simp [Nat.mul_add, Nat.mul_assoc, Nat.mul_comm, Nat.add_assoc]

theorem value_injective {as bs : List Bool} (hl : as.length = bs.length)
    (hv : value as = value bs) : as = bs := by
  induction as generalizing bs with
  | nil => cases bs <;> simp_all
  | cons a rest ih =>
    cases bs with
    | nil => simp_all
    | cons b tail =>
      have len : rest.length = tail.length := by simpa using hl
      have vals : value rest = value tail := by
        cases a <;> cases b <;> simp [value, digit] at hv <;> omega
      have bit : a = b := by
        cases a <;> cases b <;> simp_all [value, digit] <;> omega
      rw [bit, ih len vals]

end QKF.Targets
