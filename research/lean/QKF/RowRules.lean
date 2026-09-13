import Std

/-! A small, explicit fragment of Paper I: forced rows on P({0,1}).
The two coordinates are membership of false and true. No equations are
postulated about unnamed elements of arbitrary algebras. -/
namespace QKF

abbrev Carrier := Bool × Bool

def cup (a b : Carrier) : Carrier := (a.1 || b.1, a.2 || b.2)
def cap (a b : Carrier) : Carrier := (a.1 && b.1, a.2 && b.2)
def atom (b : Bool) : Carrier := if b then (false, true) else (true, false)
def empty : Carrier := (false, false)
def full : Carrier := (true, true)
def mem (p : Carrier) (b : Bool) : Bool := if b then p.2 else p.1

def PreservesCup (h : Carrier → Carrier) : Prop :=
  ∀ a b, h (cup a b) = cup (h a) (h b)
def PreservesCap (h : Carrier → Carrier) : Prop :=
  ∀ a b, h (cap a b) = cap (h a) (h b)

inductive Forced (supplied : Carrier → Carrier → Prop) : Carrier → Carrier → Prop
  | given {a b} : supplied a b → Forced supplied a b
  | union {a b x y} : Forced supplied a x → Forced supplied b y →
      Forced supplied (cup a b) (cup x y)
  | intersection {a b x y} : Forced supplied a x → Forced supplied b y →
      Forced supplied (cap a b) (cap x y)

theorem forced_sound (supplied : Carrier → Carrier → Prop)
    (h : Carrier → Carrier) (hu : PreservesCup h) (hi : PreservesCap h)
    (hs : ∀ a b, supplied a b → h a = b)
    {a b : Carrier} (proof : Forced supplied a b) : h a = b := by
  induction proof with
  | given e => exact hs _ _ e
  | union _ _ ih₁ ih₂ => rw [hu, ih₁, ih₂]
  | intersection _ _ ih₁ ih₂ => rw [hi, ih₁, ih₂]

theorem forced_no_conflict (supplied : Carrier → Carrier → Prop)
    (h : Carrier → Carrier) (hu : PreservesCup h) (hi : PreservesCap h)
    (hs : ∀ a b, supplied a b → h a = b)
    {a b c : Carrier} (p : Forced supplied a b) (q : Forced supplied a c) : b = c :=
  (forced_sound supplied h hu hi hs p).symm.trans
    (forced_sound supplied h hu hi hs q)

theorem atoms_force_row (h k : Carrier → Carrier)
    (hu : PreservesCup h) (hi : PreservesCap h)
    (ku : PreservesCup k) (ki : PreservesCap k)
    (h₀ : h (atom false) = k (atom false))
    (h₁ : h (atom true) = k (atom true)) : ∀ p, h p = k p := by
  intro ⟨x, y⟩
  cases x <;> cases y
  · change h (cap (atom false) (atom true)) = k (cap (atom false) (atom true))
    rw [hi, ki, h₀, h₁]
  · exact h₁
  · exact h₀
  · change h (cup (atom false) (atom true)) = k (cup (atom false) (atom true))
    rw [hu, ku, h₀, h₁]

def rowKernel (h : Carrier → Carrier) (a b : Carrier) : Prop := h a = h b

theorem rowKernel_operations (h : Carrier → Carrier)
    (hu : PreservesCup h) (hi : PreservesCap h)
    {a b c d : Carrier} (hab : rowKernel h a b) (hcd : rowKernel h c d) :
    rowKernel h (cup a c) (cup b d) ∧ rowKernel h (cap a c) (cap b d) := by
  change h a = h b at hab
  change h c = h d at hcd
  constructor
  · change h (cup a c) = h (cup b d)
    rw [hu, hu, hab, hcd]
  · change h (cap a c) = h (cap b d)
    rw [hi, hi, hab, hcd]

end QKF
