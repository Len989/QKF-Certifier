import Std

/-! Run 4 candidate: a finite-source-independent interpreter for the typed target
observations from run 2. No historical physical carry phases or row table occur
here. Generated data supplies a source factor, not its desired target property.
This source must be compiled before any machine-checked claim is made. -/
namespace QKFTarget

inductive Cmp | lt | eq | gt deriving DecidableEq, Repr
inductive Var | must | may | seed | alternative | output deriving DecidableEq, Repr
abbrev Env := Var → Bool

inductive Word where
  | var : Var → Word
  | zero | ones
  | bnot : Word → Word
  | band : Word → Word → Word
  | bor : Word → Word → Word
  | bxor : Word → Word → Word
  deriving DecidableEq, Repr

def bitEval : Word → Env → Bool
  | .var v, e => e v
  | .zero, _ => false
  | .ones, _ => true
  | .bnot a, e => !(bitEval a e)
  | .band a b, e => bitEval a e && bitEval b e
  | .bor a b, e => bitEval a e || bitEval b e
  | .bxor a b, e => bitEval a e != bitEval b e

inductive Kind | eq | subset | disjoint | order deriving DecidableEq, Repr
structure Atom where
  kind : Kind
  left : Word
  right : Word
  deriving DecidableEq, Repr
inductive Value | flag : Bool → Value | order : Cmp → Value deriving DecidableEq, Repr

def highCmp (a b : Bool) (old : Cmp) : Cmp :=
  if a == b then old else if a then .gt else .lt

def atomStart (a : Atom) : Value :=
  match a.kind with | .order => .order .eq | _ => .flag true

def atomStep (a : Atom) (old : Value) (e : Env) : Value :=
  let l := bitEval a.left e
  let r := bitEval a.right e
  match a.kind, old with
  | .order, .order c => .order (highCmp l r c)
  | .eq, .flag b => .flag (b && (l == r))
  | .subset, .flag b => .flag (b && (!l || r))
  | .disjoint, .flag b => .flag (b && !(l && r))
  | _, _ => .flag false

inductive Formula where
  | literal : Bool → Formula
  | query : Nat → Formula
  | lt : Nat → Formula
  | le : Nat → Formula
  | neg : Formula → Formula
  | conj : Formula → Formula → Formula
  | disj : Formula → Formula → Formula
  | implies : Formula → Formula → Formula
  deriving DecidableEq, Repr

def eval : Formula → List Value → Bool
  | .literal b, _ => b
  | .query i, v => match v[i]? with | some (.flag b) => b | _ => false
  | .lt i, v => match v[i]? with | some (.order .lt) => true | _ => false
  | .le i, v => match v[i]? with | some (.order .lt) | some (.order .eq) => true | _ => false
  | .neg f, v => !(eval f v)
  | .conj a b, v => eval a v && eval b v
  | .disj a b, v => eval a v || eval b v
  | .implies a b, v => !(eval a v) || eval b v

structure Program where
  atoms : List Atom
  premise : Formula
  target : Formula
  deriving DecidableEq, Repr

abbrev Column := Fin 6
abbrev Input := Fin 4
/- Six complete columns (must,may,seed,competitor), low bit first. -/
def mustBit (c : Column) : Bool := c.val == 5
def mayBit (c : Column) : Bool := c.val != 0
def seedBit (c : Column) : Bool := c.val == 3 || c.val == 4 || c.val == 5
def rivalBit (c : Column) : Bool := c.val == 2 || c.val == 4 || c.val == 5
def project (c : Column) : Input :=
  if c.val == 0 then 0 else if c.val < 3 then 1 else if c.val < 5 then 2 else 3

def allowed (m a x : Bool) : Bool := (!m || x) && (a || !x)

theorem columns_legal : ∀ c : Column,
    allowed (mustBit c) (mayBit c) (seedBit c) = true ∧
    allowed (mustBit c) (mayBit c) (rivalBit c) = true := by decide

theorem columns_complete : ∀ m a g z : Bool,
    allowed m a g = true → allowed m a z = true →
    ∃ c : Column, mustBit c = m ∧ mayBit c = a ∧ seedBit c = g ∧ rivalBit c = z := by
  intro m a g z hg hz
  cases m <;> cases a <;> cases g <;> cases z <;> simp_all [allowed]
  all_goals first
    | exact ⟨0, by decide⟩
    | exact ⟨1, by decide⟩
    | exact ⟨2, by decide⟩
    | exact ⟨3, by decide⟩
    | exact ⟨4, by decide⟩
    | exact ⟨5, by decide⟩

structure Machine (n : Nat) where
  initial : Fin n
  cell : Fin n → Input → Bool × Fin n

def environment (c : Column) (y : Bool) : Env
  | .must => mustBit c
  | .may => mayBit c
  | .seed => seedBit c
  | .alternative => rivalBit c
  | .output => y

structure Observation (n : Nat) where
  source : Fin n
  seen : Bool
  values : List Value
  deriving DecidableEq, Repr

def start (m : Machine n) (p : Program) : Observation n :=
  ⟨m.initial, false, p.atoms.map atomStart⟩

def step (m : Machine n) (p : Program) (s : Observation n) (c : Column) : Observation n :=
  let a := m.cell s.source (project c)
  ⟨a.2, true, List.zipWith (fun atom old => atomStep atom old (environment c a.1)) p.atoms s.values⟩

def good (p : Program) (s : Observation n) : Bool :=
  !s.seen || !(eval p.premise s.values) || eval p.target s.values

def run {S A : Type} (f : S → A → S) (s : S) : List A → S
  | [] => s
  | a :: xs => run f (f s a) xs

theorem run_relation {S T A : Type} (f : S → A → S) (g : T → A → T)
    (R : S → T → Prop) (preserves : ∀ s t, R s t → ∀ a, R (f s a) (g t a))
    {s : S} {t : T} (h : R s t) (xs : List A) : R (run f s xs) (run g t xs) := by
  induction xs generalizing s t with
  | nil => exact h
  | cons a xs ih => exact ih (preserves s t h a)

structure Certificate (n k : Nat) where
  states : Fin k → Observation n
  edges : Fin k → Column → Fin k
  initial : Fin k

/- The checker recomputes every edge with the caller's fixed machine/program. -/
def Accepted (m : Machine n) (p : Program) (c : Certificate n k) : Prop :=
  c.states c.initial = start m p ∧
  (∀ i a, step m p (c.states i) a = c.states (c.edges i a)) ∧
  (∀ i, good p (c.states i) = true)

instance (m : Machine n) (p : Program) (c : Certificate n k) : Decidable (Accepted m p c) :=
  by unfold Accepted; infer_instance

theorem closed_certificate_sound (m : Machine n) (p : Program) (c : Certificate n k)
    (h : Accepted m p c) (xs : List Column) : good p (run (step m p) (start m p) xs) = true := by
  have all : ∀ (ys : List Column) (i : Fin k), good p (run (step m p) (c.states i) ys) = true := by
    intro ys
    induction ys with
    | nil => intro i; exact h.2.2 i
    | cons a ys ih =>
      intro i
      rw [run, h.2.1 i a]
      exact ih (c.edges i a)
  rw [← h.1]
  exact all xs c.initial

/- No target-name dispatch is part of step/eval/Accepted. This fixed external
formula is used only to bind the numerical-successor specialization. -/
def successorProgram : Program :=
  { atoms := [⟨.subset, .var .must, .var .output⟩,
              ⟨.subset, .var .output, .var .may⟩,
              ⟨.eq, .var .seed, .var .may⟩,
              ⟨.order, .var .seed, .var .output⟩,
              ⟨.order, .var .seed, .var .alternative⟩,
              ⟨.order, .var .output, .var .alternative⟩,
              ⟨.eq, .var .output, .var .must⟩],
    premise := .literal true,
    target := .conj (.query 0) (.conj (.query 1)
      (.conj (.implies (.neg (.query 2)) (.lt 3))
        (.conj (.implies (.lt 4) (.le 5)) (.implies (.query 2) (.query 6))))) }

end QKFTarget
