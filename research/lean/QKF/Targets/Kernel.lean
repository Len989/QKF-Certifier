import QKF.Targets.Rules

namespace QKF.Targets

abbrev Input := Fin 4
abbrev Column := Fin 6

def must (i : Input) : Bool := i.val == 3
def may (i : Input) : Bool := i.val != 0
def seed (i : Input) : Bool := i.val >= 2

def input (c : Column) : Input :=
  if c.val == 0 then 0 else if c.val <= 2 then 1 else if c.val <= 4 then 2 else 3

def alternative (c : Column) : Bool := c.val == 2 || c.val == 4 || c.val == 5

def allowed (m a v : Bool) : Bool := (!m || v) && (a || !v)

theorem columns_legal : ∀ c : Column,
    allowed (must (input c)) (may (input c)) (seed (input c)) = true ∧
    allowed (must (input c)) (may (input c)) (alternative c) = true := by decide

theorem columns_complete : ∀ m a g z : Bool,
    allowed m a g = true → allowed m a z = true →
    ∃ c : Column, must (input c) = m ∧ may (input c) = a ∧
      seed (input c) = g ∧ alternative c = z := by
  intro m a g z hg hz
  cases m <;> cases a <;> cases g <;> cases z <;> simp_all [allowed]
  all_goals first
    | exact ⟨0, by decide⟩
    | exact ⟨1, by decide⟩
    | exact ⟨2, by decide⟩
    | exact ⟨3, by decide⟩
    | exact ⟨4, by decide⟩
    | exact ⟨5, by decide⟩

/- The machine cannot inspect the independent alternative: its argument is Input. -/
structure Machine (k : Nat) where
  initial : Fin k
  step : Fin k → Input → Bool × Fin k

def environment {k : Nat} (m : Machine k) (s : Fin k) (c : Column) : Env
  | .must => must (input c)
  | .may => may (input c)
  | .seed => seed (input c)
  | .alternative => alternative c
  | .output => (m.step s (input c)).1
  | .bound => false

structure Execution (k : Nat) where
  source : Fin k
  history : List Env

def execStart {k : Nat} (m : Machine k) : Execution k := ⟨m.initial, []⟩

def execStep {k : Nat} (m : Machine k) (s : Execution k) (c : Column) : Execution k :=
  ⟨(m.step s.source (input c)).2, s.history ++ [environment m s.source c]⟩

def execute {k : Nat} (m : Machine k) (xs : List Column) : Execution k :=
  QKF.run (execStep m) (execStart m) xs

structure Joint (n k : Nat) where
  source : Fin k
  nonempty : Bool
  answers : Fin n → Answer

def jointEq {n k : Nat} (s t : Joint n k) : Prop :=
  s.source = t.source ∧ s.nonempty = t.nonempty ∧ ∀ i, s.answers i = t.answers i

instance {n k : Nat} (s t : Joint n k) : Decidable (jointEq s t) := by
  unfold jointEq
  infer_instance

theorem joint_ext {n k : Nat} {s t : Joint n k} (h : jointEq s t) : s = t := by
  have ho : s.answers = t.answers := funext h.2.2
  cases s
  cases t
  simp only [jointEq] at h
  simp only at ho
  cases h.1
  cases h.2.1
  cases ho
  rfl

def observe {n k : Nat} (p : Program n) (s : Execution k) : Joint n k :=
  ⟨s.source, !s.history.isEmpty, meaning p s.history⟩

def jointStart {n k : Nat} (m : Machine k) (p : Program n) : Joint n k :=
  ⟨m.initial, false, fun i => atomStart (p.atoms i)⟩

def jointStep {n k : Nat} (m : Machine k) (p : Program n)
    (s : Joint n k) (c : Column) : Joint n k :=
  ⟨(m.step s.source (input c)).2, true, advance p s.answers (environment m s.source c)⟩

def good {n k : Nat} (p : Program n) (s : Joint n k) : Bool :=
  !s.nonempty || !(evaluate p.precondition s.answers) || evaluate p.obligation s.answers

theorem observe_start {n k : Nat} (m : Machine k) (p : Program n) :
    observe p (execStart m) = jointStart m p := by
  apply joint_ext
  refine ⟨rfl, rfl, ?_⟩
  intro i
  exact atom_empty (p.atoms i)

theorem observe_step {n k : Nat} (m : Machine k) (p : Program n)
    (s : Execution k) (c : Column) :
    observe p (execStep m s c) = jointStep m p (observe p s) c := by
  apply joint_ext
  refine ⟨rfl, ?_, ?_⟩
  · cases s.history <;> rfl
  · intro i
    exact atom_snoc (p.atoms i) s.history (environment m s.source c)

structure Certificate (n k size : Nat) where
  states : Fin size → Joint n k
  initial : Fin size
  edges : Fin size → Column → Fin size

def Obligations {n k size : Nat} (m : Machine k) (p : Program n)
    (c : Certificate n k size) : Prop :=
  wellTyped p p.precondition = true ∧ wellTyped p p.obligation = true ∧
  jointEq (c.states c.initial) (jointStart m p) ∧
  (∀ i a, jointEq (jointStep m p (c.states i) a) (c.states (c.edges i a))) ∧
  (∀ i, good p (c.states i) = true)

instance {n k size : Nat} (m : Machine k) (p : Program n)
    (c : Certificate n k size) : Decidable (Obligations m p c) := by
  unfold Obligations
  infer_instance

def checkCertificate {n k size : Nat} (m : Machine k) (p : Program n)
    (c : Certificate n k size) : Bool := decide (Obligations m p c)

theorem accepted_closed {n k size : Nat} (m : Machine k) (p : Program n)
    (c : Certificate n k size) (accepted : checkCertificate m p c = true)
    (xs : List Column) : good p (QKF.run (jointStep m p) (jointStart m p) xs) = true := by
  have h : Obligations m p c := of_decide_eq_true accepted
  have first := joint_ext h.2.2.1
  rw [← first]
  exact QKF.closed_certificate_sound (jointStep m p) c.states c.edges c.initial
    (fun s => good p s = true) (fun i a => joint_ext (h.2.2.2.1 i a)) h.2.2.2.2 xs

theorem execution_length {k : Nat} (m : Machine k) (xs : List Column) (s : Execution k) :
    (QKF.run (execStep m) s xs).history.length = s.history.length + xs.length := by
  induction xs generalizing s with
  | nil => simp [QKF.run]
  | cons a rest ih =>
    rw [QKF.run, ih]
    simp [execStep, Nat.add_assoc, Nat.add_comm, Nat.add_left_comm]

/- A generic, numerical all-width theorem for ANY exported finite machine and
well-typed formula program whose complete certificate is accepted. -/
theorem accepted_all_widths {n k size : Nat} (m : Machine k) (p : Program n)
    (c : Certificate n k size) (accepted : checkCertificate m p c = true)
    (xs : List Column) (positive : xs ≠ []) : semanticGoal p (execute m xs).history = true := by
  have sim := QKF.run_simulation (execStep m) (jointStep m p) (observe p)
    (observe_step m p) xs (execStart m)
  rw [observe_start] at sim
  have hg := accepted_closed m p c accepted xs
  rw [← sim] at hg
  change good p (observe p (execute m xs)) = true at hg
  have len : (execute m xs).history.length = xs.length := by
    simpa [execute, execStart] using execution_length m xs (execStart m)
  cases hh : (execute m xs).history with
  | nil =>
    have hx : xs.length = 0 := by simpa [hh] using len.symm
    cases xs with
    | nil => exact (positive rfl).elim
    | cons a rest => simp at hx
  | cons e es =>
    simpa [good, observe, semanticGoal, hh] using hg

end QKF.Targets
