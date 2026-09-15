import QKF.Targets.Successor

namespace QKF.Targets

/- Execution projected to source inputs only. The competitor is not an input
of this function, so quantifying it cannot silently change the source answer. -/
def emitted {k : Nat} (m : Machine k) (s : Fin k) : List Input → List Bool
  | [] => []
  | i :: rest => (m.step s i).1 :: emitted m (m.step s i).2 rest

def trace {k : Nat} (m : Machine k) (s : Fin k) : List Column → List Env
  | [] => []
  | c :: rest => environment m s c :: trace m (m.step s (input c)).2 rest

theorem history_run {k : Nat} (m : Machine k) (xs : List Column) (s : Execution k) :
    (QKF.run (execStep m) s xs).history = s.history ++ trace m s.source xs := by
  induction xs generalizing s with
  | nil => simp [QKF.run, trace]
  | cons a rest ih =>
    rw [QKF.run, ih]
    simp [execStep, trace, List.append_assoc]

theorem execute_history {k : Nat} (m : Machine k) (xs : List Column) :
    (execute m xs).history = trace m m.initial xs := by
  simpa [execute, execStart] using history_run m xs (execStart m)

theorem trace_read {k : Nat} (m : Machine k) (v : Variable) (f : Column → Bool)
    (hf : ∀ s c, environment m s c v = f c) (xs : List Column) (s : Fin k) :
    (trace m s xs).map (fun e => e v) = xs.map f := by
  induction xs generalizing s with
  | nil => rfl
  | cons a rest ih => simp [trace, hf, ih]

theorem trace_output {k : Nat} (m : Machine k) (xs : List Column) (s : Fin k) :
    (trace m s xs).map (fun e => e .output) = emitted m s (xs.map input) := by
  induction xs generalizing s with
  | nil => rfl
  | cons a rest ih => simp [trace, emitted, environment, ih]

@[simp] theorem number_execute_must {k : Nat} (m : Machine k) (xs : List Column) :
    number (.var .must) (execute m xs).history = value ((xs.map input).map must) := by
  rw [execute_history]
  simp only [number, bit]
  rw [trace_read m .must (fun c => must (input c)) (fun _ _ => rfl)]
  simp [List.map_map]

@[simp] theorem number_execute_may {k : Nat} (m : Machine k) (xs : List Column) :
    number (.var .may) (execute m xs).history = value ((xs.map input).map may) := by
  rw [execute_history]
  simp only [number, bit]
  rw [trace_read m .may (fun c => may (input c)) (fun _ _ => rfl)]
  simp [List.map_map]

@[simp] theorem number_execute_seed {k : Nat} (m : Machine k) (xs : List Column) :
    number (.var .seed) (execute m xs).history = value ((xs.map input).map seed) := by
  rw [execute_history]
  simp only [number, bit]
  rw [trace_read m .seed (fun c => seed (input c)) (fun _ _ => rfl)]
  simp [List.map_map]

@[simp] theorem number_execute_alternative {k : Nat} (m : Machine k) (xs : List Column) :
    number (.var .alternative) (execute m xs).history = value (xs.map alternative) := by
  rw [execute_history]
  simp only [number, bit]
  exact congrArg value (trace_read m .alternative alternative (fun _ _ => rfl) xs m.initial)

@[simp] theorem number_execute_output {k : Nat} (m : Machine k) (xs : List Column) :
    number (.var .output) (execute m xs).history = value (emitted m m.initial (xs.map input)) := by
  rw [execute_history]
  simp only [number, bit]
  exact congrArg value (trace_output m xs m.initial)

theorem output_independent {k : Nat} (m : Machine k) (xs ys : List Column)
    (same : xs.map input = ys.map input) :
    number (.var .output) (execute m xs).history =
      number (.var .output) (execute m ys).history := by
  simp only [number_execute_output, same]

/- Exactly legal output bits, with simultaneous equal lengths. -/
def AdmissibleBits (is : List Input) (bs : List Bool) : Prop :=
  List.Forall₂ (fun i b => allowed (must i) (may i) b = true) is bs

/- A numerical carrier: all numbers represented by the legal masked bit lists.
No source execution or certificate is used in this definition. -/
def Masked (is : List Input) (z : Nat) : Prop :=
  ∃ bs, AdmissibleBits is bs ∧ value bs = z

theorem column_for_bit : ∀ (i : Input) (b : Bool),
    allowed (must i) (may i) b = true →
    ∃ c : Column, input c = i ∧ alternative c = b := by decide

theorem encode_columns {is : List Input} {bs : List Bool} (h : AdmissibleBits is bs) :
    ∃ cs : List Column, cs.map input = is ∧ cs.map alternative = bs := by
  induction h with
  | nil => exact ⟨[], rfl, rfl⟩
  | @cons i b rest tail hb ht ih =>
    obtain ⟨c, hi, hz⟩ := column_for_bit i b hb
    obtain ⟨cs, his, hzs⟩ := ih
    exact ⟨c :: cs, by simp [hi, his], by simp [hz, hzs]⟩

theorem legal_extrema_bits : ∀ i : Input,
    allowed (must i) (may i) (must i) = true ∧
    allowed (must i) (may i) (may i) = true ∧
    allowed (must i) (may i) (seed i) = true := by decide

theorem extrema_admissible (is : List Input) :
    AdmissibleBits is (is.map must) ∧ AdmissibleBits is (is.map may) ∧
    AdmissibleBits is (is.map seed) := by
  induction is with
  | nil => exact ⟨.nil, .nil, .nil⟩
  | cons i rest ih =>
    have h := legal_extrema_bits i
    exact ⟨.cons h.1 ih.1, .cons h.2.1 ih.2.1, .cons h.2.2 ih.2.2⟩

theorem digit_limits : ∀ (i : Input) (b : Bool),
    allowed (must i) (may i) b = true →
    digit (must i) ≤ digit b ∧ digit b ≤ digit (may i) := by decide

theorem mask_limits {is : List Input} {bs : List Bool} (h : AdmissibleBits is bs) :
    value (is.map must) ≤ value bs ∧ value bs ≤ value (is.map may) := by
  induction h with
  | nil => simp [value]
  | @cons i b rest tail hb ht ih =>
    have hd := digit_limits i b hb
    simp only [List.map_cons, value]
    omega

theorem masked_extrema (is : List Input) :
    Masked is (value (is.map must)) ∧ Masked is (value (is.map may)) ∧
    (∀ z, Masked is z → value (is.map must) ≤ z ∧ z ≤ value (is.map may)) := by
  have h := extrema_admissible is
  refine ⟨⟨is.map must, h.1, rfl⟩, ⟨is.map may, h.2.1, rfl⟩, ?_⟩
  intro z hz
  obtain ⟨bs, hb, rfl⟩ := hz
  exact mask_limits hb

theorem greater_exists_iff (is : List Input) :
    (∃ z, Masked is z ∧ value (is.map seed) < z) ↔
      value (is.map seed) ≠ value (is.map may) := by
  have bounds := mask_limits (extrema_admissible is).2.2
  have extrema := masked_extrema is
  constructor
  · rintro ⟨z, hz, hg⟩
    have upper := (extrema.2.2 z hz).2
    omega
  · intro hn
    exact ⟨value (is.map may), extrema.2.1, by omega⟩

theorem trace_admissible {k : Nat} (m : Machine k) (xs : List Column) (s : Fin k)
    (hl : support (.var .must) (.var .output) (trace m s xs) = true)
    (hu : support (.var .output) (.var .may) (trace m s xs) = true) :
    AdmissibleBits (xs.map input) (emitted m s (xs.map input)) := by
  induction xs generalizing s with
  | nil => exact .nil
  | cons c rest ih =>
    simp only [support, trace, List.all_cons, Bool.and_eq_true, bit, environment] at hl hu
    apply List.Forall₂.cons
    · exact Bool.and_eq_true.mpr ⟨hl.1, by simpa [Bool.or_comm] using hu.1⟩
    · exact ih _ hl.2 hu.2

/- Exact numerical cyclic least-element property, including the no-greater case. -/
def CyclicSuccessor (is : List Input) (y : Nat) : Prop :=
  Masked is y ∧
  ((∃ z, Masked is z ∧ value (is.map seed) < z) →
    value (is.map seed) < y ∧
      ∀ z, Masked is z → value (is.map seed) < z → y ≤ z) ∧
  ((¬ ∃ z, Masked is z ∧ value (is.map seed) < z) → y = value (is.map must))

theorem cyclic_successor_all_widths {k size : Nat} (m : Machine k)
    (cert : Certificate 7 k size) (accepted : checkCertificate m successorProgram cert = true)
    (is : List Input) (positive : is ≠ []) :
    CyclicSuccessor is (value (emitted m m.initial is)) := by
  obtain ⟨cs, hc, _⟩ := encode_columns (extrema_admissible is).1
  have nonempty : cs ≠ [] := by intro he; apply positive; simpa [he] using hc.symm
  obtain ⟨hl, hu, hg, hm, hw⟩ := successor_from_certificate m cert accepted cs nonempty
  have member := trace_admissible m cs m.initial
    (by simpa [execute_history] using hl) (by simpa [execute_history] using hu)
  have greater : value (is.map seed) ≠ value (is.map may) →
      value (is.map seed) < value (emitted m m.initial is) := by simpa [hc] using hg
  have wrap : value (is.map seed) = value (is.map may) →
      value (emitted m m.initial is) = value (is.map must) := by simpa [hc] using hw
  refine ⟨⟨emitted m m.initial is, by simpa [hc] using member, rfl⟩, ?_, ?_⟩
  · intro hex
    refine ⟨greater ((greater_exists_iff is).mp hex), ?_⟩
    intro z hz hgz
    obtain ⟨bs, hb, hv⟩ := hz
    obtain ⟨zs, hi, ha⟩ := encode_columns hb
    have nz : zs ≠ [] := by intro he; apply positive; simpa [he] using hi.symm
    have hzpost := (successor_from_certificate m cert accepted zs nz).2.2.2.1
    have hmz : value (is.map seed) < z → value (emitted m m.initial is) ≤ z := by
      simpa [hi, ha, hv] using hzpost
    exact hmz hgz
  · intro none
    apply wrap
    have hn : ¬ value (is.map seed) ≠ value (is.map may) := by
      intro hne
      exact none ((greater_exists_iff is).mpr hne)
    omega

end QKF.Targets
