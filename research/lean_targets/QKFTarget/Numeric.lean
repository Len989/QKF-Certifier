import QKFTarget.Core
import Lean.Elab.Tactic.Omega

/-! Numerical semantics is separate from the finite observation interpreter.
Words are coordinatewise expressions on a finite sequence of bit environments.
The natural-number value is accumulated with weights 2^position. Mask inclusion
is pointwise inclusion of these words; it is not a finite-width oracle. -/
namespace QKFTarget

def digit (b : Bool) : Nat := if b then 1 else 0
def cmpNat (a b : Nat) : Cmp := if a < b then .lt else if a = b then .eq else .gt

theorem cmp_high {a b base : Nat} (ha : a < base) (hb : b < base) (x y : Bool) :
    cmpNat (a + digit x * base) (b + digit y * base) = highCmp x y (cmpNat a b) := by
  cases x <;> cases y
  · simp [digit, highCmp]
  · have h : a < b + base := by omega
    simp [digit, highCmp, cmpNat, h]
  · have h₁ : ¬ a + base < b := by omega
    have h₂ : a + base ≠ b := by omega
    simp [digit, highCmp, cmpNat, h₁, h₂]
  · simp [digit, highCmp, cmpNat]

theorem equality_high {a b base : Nat} (ha : a < base) (hb : b < base) (x y : Bool) :
    (a + digit x * base = b + digit y * base) ↔ (a = b ∧ x = y) := by
  cases x <;> cases y <;> simp [digit] <;> omega

theorem digit_bound {a base : Nat} (ha : a < base) (b : Bool) :
    a + digit b * base < base * 2 := by
  cases b <;> simp [digit] <;> omega

structure Numbers where
  width : Nat
  value : Word → Nat
  trace : List Env

def numberStart : Numbers := ⟨0, fun _ => 0, []⟩
def numberStep (s : Numbers) (e : Env) : Numbers :=
  ⟨s.width + 1, fun w => s.value w + digit (bitEval w e) * 2 ^ s.width, s.trace ++ [e]⟩
def Bounded (s : Numbers) : Prop := ∀ w, s.value w < 2 ^ s.width

theorem start_bounded : Bounded numberStart := by
  intro w
  change 0 < 1
  decide

theorem step_bounded (s : Numbers) (h : Bounded s) (e : Env) : Bounded (numberStep s e) := by
  intro w
  change s.value w + digit (bitEval w e) * 2 ^ s.width < 2 ^ (s.width + 1)
  rw [Nat.pow_succ]
  exact digit_bound (h w) _

def subsetBits (s : Numbers) (l r : Word) : Bool :=
  s.trace.all (fun e => !(bitEval l e) || bitEval r e)
def disjointBits (s : Numbers) (l r : Word) : Bool :=
  s.trace.all (fun e => !(bitEval l e && bitEval r e))

def numericAtom (a : Atom) (s : Numbers) : Value :=
  match a.kind with
  | .eq => .flag (decide (s.value a.left = s.value a.right))
  | .subset => .flag (subsetBits s a.left a.right)
  | .disjoint => .flag (disjointBits s a.left a.right)
  | .order => .order (cmpNat (s.value a.left) (s.value a.right))

theorem atom_initial (a : Atom) : atomStart a = numericAtom a numberStart := by
  cases a with
  | mk k l r => cases k <;> rfl

theorem atom_numerical_step (a : Atom) (s : Numbers) (h : Bounded s) (e : Env) :
    atomStep a (numericAtom a s) e = numericAtom a (numberStep s e) := by
  cases a with
  | mk k l r =>
    cases k with
    | eq =>
      have he := equality_high (h l) (h r) (bitEval l e) (bitEval r e)
      simp [atomStep, numericAtom, numberStep, he]
      cases bitEval l e <;> cases bitEval r e <;> rfl
    | subset => simp [atomStep, numericAtom, subsetBits, numberStep, List.all_append]
    | disjoint => simp [atomStep, numericAtom, disjointBits, numberStep, List.all_append]
    | order =>
      change Value.order (highCmp (bitEval l e) (bitEval r e) (cmpNat (s.value l) (s.value r))) = _
      rw [← cmp_high (h l) (h r)]
      rfl

theorem zip_map {A B C : Type} (xs : List A) (f : A → B) (g : A → B → C) :
    List.zipWith g xs (xs.map f) = xs.map (fun a => g a (f a)) := by
  induction xs with
  | nil => rfl
  | cons a xs ih => simp [ih]

structure Concrete (n : Nat) where
  source : Fin n
  numbers : Numbers

def concreteStart (m : Machine n) : Concrete n := ⟨m.initial, numberStart⟩
def concreteStep (m : Machine n) (s : Concrete n) (c : Column) : Concrete n :=
  let action := m.cell s.source (project c)
  ⟨action.2, numberStep s.numbers (environment c action.1)⟩

structure Agrees (p : Program) (o : Observation n) (s : Concrete n) : Prop where
  source : o.source = s.source
  seen : o.seen = decide (0 < s.numbers.width)
  values : o.values = p.atoms.map (fun a => numericAtom a s.numbers)
  bounded : Bounded s.numbers

theorem initial_agrees (m : Machine n) (p : Program) : Agrees p (start m p) (concreteStart m) := by
  constructor
  · rfl
  · rfl
  · change p.atoms.map atomStart = p.atoms.map (fun a => numericAtom a numberStart)
    exact List.map_congr_left (fun a _ => atom_initial a)
  · exact start_bounded

theorem step_agrees (m : Machine n) (p : Program) (o : Observation n) (s : Concrete n)
    (h : Agrees p o s) (c : Column) : Agrees p (step m p o c) (concreteStep m s c) := by
  constructor
  · simp only [step, concreteStep, h.source]
  · simp [step, concreteStep, numberStep]
  · simp only [step, concreteStep, h.source, h.values, zip_map]
    apply List.map_congr_left
    intro a _
    exact atom_numerical_step a s.numbers h.bounded _
  · exact step_bounded s.numbers h.bounded _

theorem all_lengths_agree (m : Machine n) (p : Program) (xs : List Column) :
    Agrees p (run (step m p) (start m p) xs) (run (concreteStep m) (concreteStart m) xs) :=
  run_relation (step m p) (concreteStep m) (Agrees p) (step_agrees m p) (initial_agrees m p) xs

theorem concrete_width (m : Machine n) (xs : List Column) (s : Concrete n) :
    (run (concreteStep m) s xs).numbers.width = s.numbers.width + xs.length := by
  induction xs generalizing s with
  | nil => simp [run]
  | cons c xs ih =>
    rw [run, ih]
    simp [concreteStep, numberStep, Nat.add_assoc, Nat.add_comm]

/- A numerical word formula for every positive length, for any source factor,
any formula and any accepted finite certificate. Source parsing is not assumed
correct by this theorem; the exported machine remains its explicit parameter. -/
theorem numerical_formula_all_widths (m : Machine n) (p : Program) (c : Certificate n k)
    (hc : Accepted m p c) (xs : List Column) (positive : 0 < xs.length)
    (premise : eval p.premise
      (p.atoms.map (fun a => numericAtom a (run (concreteStep m) (concreteStart m) xs).numbers)) = true) :
    eval p.target
      (p.atoms.map (fun a => numericAtom a (run (concreteStep m) (concreteStart m) xs).numbers)) = true := by
  have h := all_lengths_agree m p xs
  have hg := closed_certificate_sound m p c hc xs
  have hw : 0 < (run (concreteStep m) (concreteStart m) xs).numbers.width := by
    simpa [concrete_width, concreteStart, numberStart] using positive
  unfold good at hg
  rw [h.seen, h.values] at hg
  simpa [hw, premise] using hg

/- Output legality is a pointwise mask statement on the complete emitted trace;
the order and equality obligations below use actual natural-number values. -/
def SuccessorNumeric (s : Numbers) : Prop :=
  subsetBits s (.var .must) (.var .output) = true ∧
  subsetBits s (.var .output) (.var .may) = true ∧
  (s.value (.var .seed) ≠ s.value (.var .may) → s.value (.var .seed) < s.value (.var .output)) ∧
  (s.value (.var .seed) < s.value (.var .alternative) → s.value (.var .output) ≤ s.value (.var .alternative)) ∧
  (s.value (.var .seed) = s.value (.var .may) → s.value (.var .output) = s.value (.var .must))

def cmpLt : Cmp → Bool | .lt => true | _ => false
def cmpLe : Cmp → Bool | .lt | .eq => true | .gt => false

theorem cmpNat_lt_value (a b : Nat) : cmpLt (cmpNat a b) = decide (a < b) := by
  unfold cmpNat
  split
  · simp_all [cmpLt]
  · split <;> simp_all [cmpLt]

theorem cmpNat_le_value (a b : Nat) : cmpLe (cmpNat a b) = decide (a ≤ b) := by
  unfold cmpNat
  split
  · have hab : a ≤ b := by omega
    simp_all [cmpLe]
  · split
    · subst b; simp [cmpLe]
    · have hab : ¬ a ≤ b := by omega
      simp_all [cmpLe]

theorem successor_formula_numerical (s : Numbers) :
    eval successorProgram.target (successorProgram.atoms.map (fun a => numericAtom a s)) = true ↔
      SuccessorNumeric s := by
  have hgy := cmpNat_lt_value (s.value (.var .seed)) (s.value (.var .output))
  have hgz := cmpNat_lt_value (s.value (.var .seed)) (s.value (.var .alternative))
  have hyz := cmpNat_le_value (s.value (.var .output)) (s.value (.var .alternative))
  cases egy : cmpNat (s.value (.var .seed)) (s.value (.var .output)) <;>
    cases egz : cmpNat (s.value (.var .seed)) (s.value (.var .alternative)) <;>
    cases eyz : cmpNat (s.value (.var .output)) (s.value (.var .alternative)) <;>
    simp_all [successorProgram, eval, numericAtom, SuccessorNumeric, cmpLt, cmpLe]
  all_goals
    cases Nat.decEq (s.value (.var .seed)) (s.value (.var .may)) with
    | isTrue heq => simp_all <;> omega
    | isFalse hne => simp_all <;> omega

theorem cyclic_successor_all_widths (m : Machine n) (c : Certificate n k)
    (hc : Accepted m successorProgram c) (xs : List Column) (positive : 0 < xs.length) :
    SuccessorNumeric (run (concreteStep m) (concreteStart m) xs).numbers := by
  apply (successor_formula_numerical _).mp
  apply numerical_formula_all_widths m successorProgram c hc xs positive
  rfl

/- Pure numerical endpoint argument. It includes the singleton/wrap case and
uses an independent universally quantified competitor, never a second source run.
The legal masked set must instantiate these stated extrema premises. -/
theorem cyclic_extrema_characterization (L : Nat → Prop) (minimum maximum seed output : Nat)
    (seedLegal : L seed) (maxLegal : L maximum) (bounded : ∀ x, L x → x ≤ maximum)
    (outputLegal : L output)
    (advance : seed ≠ maximum → seed < output)
    (minimal : ∀ z, L z → seed < z → output ≤ z)
    (wrap : seed = maximum → output = minimum) :
    L output ∧
    ((∃ z, L z ∧ seed < z) → seed < output ∧ ∀ z, L z → seed < z → output ≤ z) ∧
    ((¬ ∃ z, L z ∧ seed < z) → output = minimum) := by
  refine ⟨outputLegal, ?_, ?_⟩
  · intro hex
    obtain ⟨z, hz, hgreater⟩ := hex
    have hbound := bounded z hz
    have hne : seed ≠ maximum := by omega
    exact ⟨advance hne, minimal⟩
  · intro hnone
    have hle := bounded seed seedLegal
    have hnlt : ¬ seed < maximum := by
      intro hlt
      exact hnone ⟨maximum, maxLegal, hlt⟩
    have heq : seed = maximum := by omega
    exact wrap heq

end QKFTarget
