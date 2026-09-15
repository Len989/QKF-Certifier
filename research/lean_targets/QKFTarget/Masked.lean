import QKFTarget.Numeric
import QKFTarget.Exported

/-! Exact masked-word endpoint for the accepted target-observation kernel.
Adapted from the input/competitor bridge of PR #7 to the independent #8 kernel.
No second certificate checker, source machine or physical carry model is added.
Lists contain least significant bits first; every admissible competitor is
represented by the existing complete column alphabet. -/
namespace QKFTarget.MaskedWords

def inputMust (i : Input) : Bool := i.val == 3
def inputMay (i : Input) : Bool := i.val != 0
def inputSeed (i : Input) : Bool := i.val == 2 || i.val == 3

@[simp] theorem project_must : ∀ c : Column, inputMust (project c) = mustBit c := by decide
@[simp] theorem project_may : ∀ c : Column, inputMay (project c) = mayBit c := by decide
@[simp] theorem project_seed : ∀ c : Column, inputSeed (project c) = seedBit c := by decide

def value : List Bool → Nat
  | [] => 0
  | b :: bs => digit b + 2 * value bs

theorem value_snoc (bs : List Bool) (b : Bool) :
    value (bs ++ [b]) = value bs + digit b * 2 ^ bs.length := by
  induction bs with
  | nil => simp [value]
  | cons a bs ih =>
    simp only [List.cons_append, value, ih, List.length_cons, Nat.pow_succ]
    simp only [Nat.mul_add]
    ac_rfl

theorem value_bound (bs : List Bool) : value bs < 2 ^ bs.length := by
  induction bs with
  | nil => decide
  | cons b bs ih =>
    have hd : digit b < 2 := by cases b <;> decide
    simp only [value, List.length_cons, Nat.pow_succ]
    omega

/- Input-only execution: an alternative cannot influence this function. -/
def emitted (m : Machine n) (s : Fin n) : List Input → List Bool
  | [] => []
  | i :: rest => (m.cell s i).1 :: emitted m (m.cell s i).2 rest

def trace (m : Machine n) (s : Fin n) : List Column → List Env
  | [] => []
  | c :: rest => environment c (m.cell s (project c)).1 ::
      trace m (m.cell s (project c)).2 rest

theorem emitted_length (m : Machine n) (s : Fin n) (is : List Input) :
    (emitted m s is).length = is.length := by
  induction is generalizing s with
  | nil => rfl
  | cons i rest ih => simp [emitted, ih]

theorem history_run (m : Machine n) (xs : List Column) (s : Concrete n) :
    (run (concreteStep m) s xs).numbers.trace = s.numbers.trace ++ trace m s.source xs := by
  induction xs generalizing s with
  | nil => simp [run, trace]
  | cons c rest ih =>
    rw [run, ih]
    simp [concreteStep, numberStep, trace, List.append_assoc]

theorem execute_history (m : Machine n) (xs : List Column) :
    (run (concreteStep m) (concreteStart m) xs).numbers.trace = trace m m.initial xs := by
  simpa [concreteStart, numberStart] using history_run m xs (concreteStart m)

structure Represents (s : Numbers) : Prop where
  width : s.width = s.trace.length
  values : ∀ w, s.value w = value (s.trace.map (bitEval w))

theorem represents_start : Represents numberStart := by
  constructor
  · rfl
  · intro w; rfl

theorem represents_step (s : Numbers) (h : Represents s) (e : Env) :
    Represents (numberStep s e) := by
  constructor
  · simp [numberStep, h.width]
  · intro w
    simp only [numberStep, List.map_append, List.map_cons, List.map_nil, value_snoc,
      List.length_map, h.width, h.values]

theorem represents_run (m : Machine n) (xs : List Column) (s : Concrete n)
    (h : Represents s.numbers) : Represents (run (concreteStep m) s xs).numbers := by
  induction xs generalizing s with
  | nil => exact h
  | cons c rest ih => exact ih (concreteStep m s c) (represents_step _ h _)

theorem executed_value (m : Machine n) (xs : List Column) (w : Word) :
    (run (concreteStep m) (concreteStart m) xs).numbers.value w =
      value ((trace m m.initial xs).map (bitEval w)) := by
  rw [(represents_run m xs (concreteStart m) represents_start).values, execute_history]

theorem trace_read (m : Machine n) (v : Var) (f : Column → Bool)
    (hf : ∀ c y, environment c y v = f c) (xs : List Column) (s : Fin n) :
    (trace m s xs).map (fun e => e v) = xs.map f := by
  induction xs generalizing s with
  | nil => rfl
  | cons c rest ih => simp [trace, hf, ih]

theorem trace_output (m : Machine n) (xs : List Column) (s : Fin n) :
    (trace m s xs).map (fun e => e .output) = emitted m s (xs.map project) := by
  induction xs generalizing s with
  | nil => rfl
  | cons c rest ih => simp [trace, emitted, environment, ih]

@[simp] theorem number_must (m : Machine n) (xs : List Column) :
    (run (concreteStep m) (concreteStart m) xs).numbers.value (.var .must) =
      value ((xs.map project).map inputMust) := by
  rw [executed_value]
  simp only [bitEval]
  rw [trace_read m .must mustBit (fun _ _ => rfl)]
  simp only [List.map_map, Function.comp_def, project_must]

@[simp] theorem number_may (m : Machine n) (xs : List Column) :
    (run (concreteStep m) (concreteStart m) xs).numbers.value (.var .may) =
      value ((xs.map project).map inputMay) := by
  rw [executed_value]
  simp only [bitEval]
  rw [trace_read m .may mayBit (fun _ _ => rfl)]
  simp only [List.map_map, Function.comp_def, project_may]

@[simp] theorem number_seed (m : Machine n) (xs : List Column) :
    (run (concreteStep m) (concreteStart m) xs).numbers.value (.var .seed) =
      value ((xs.map project).map inputSeed) := by
  rw [executed_value]
  simp only [bitEval]
  rw [trace_read m .seed seedBit (fun _ _ => rfl)]
  simp only [List.map_map, Function.comp_def, project_seed]

@[simp] theorem number_alternative (m : Machine n) (xs : List Column) :
    (run (concreteStep m) (concreteStart m) xs).numbers.value (.var .alternative) =
      value (xs.map rivalBit) := by
  rw [executed_value]
  simp only [bitEval]
  rw [trace_read m .alternative rivalBit (fun _ _ => rfl)]

@[simp] theorem number_output (m : Machine n) (xs : List Column) :
    (run (concreteStep m) (concreteStart m) xs).numbers.value (.var .output) =
      value (emitted m m.initial (xs.map project)) := by
  rw [executed_value]
  simp only [bitEval]
  rw [trace_output]

theorem output_independent (m : Machine n) (xs ys : List Column)
    (same : xs.map project = ys.map project) :
    (run (concreteStep m) (concreteStart m) xs).numbers.value (.var .output) =
      (run (concreteStep m) (concreteStart m) ys).numbers.value (.var .output) := by
  simp only [number_output, same]

/- Legal bit lists have exactly the input width. This predicate is source-free. -/
inductive AdmissibleBits : List Input → List Bool → Prop where
  | nil : AdmissibleBits [] []
  | cons {i : Input} {b : Bool} {is : List Input} {bs : List Bool} :
      allowed (inputMust i) (inputMay i) b = true → AdmissibleBits is bs →
        AdmissibleBits (i :: is) (b :: bs)

def Masked (is : List Input) (z : Nat) : Prop :=
  ∃ bs, AdmissibleBits is bs ∧ value bs = z

theorem admissible_length {is : List Input} {bs : List Bool} (h : AdmissibleBits is bs) :
    bs.length = is.length := by
  induction h with
  | nil => rfl
  | cons _ _ ih => simpa using congrArg Nat.succ ih

theorem masked_width {is : List Input} {z : Nat} (h : Masked is z) : z < 2 ^ is.length := by
  obtain ⟨bs, hb, rfl⟩ := h
  simpa only [admissible_length hb] using value_bound bs

theorem column_for_bit : ∀ (i : Input) (b : Bool),
    allowed (inputMust i) (inputMay i) b = true →
    ∃ c : Column, project c = i ∧ rivalBit c = b := by decide

theorem encode_columns {is : List Input} {bs : List Bool} (h : AdmissibleBits is bs) :
    ∃ cs : List Column, cs.map project = is ∧ cs.map rivalBit = bs := by
  induction h with
  | nil => exact ⟨[], rfl, rfl⟩
  | @cons i b rest tail hb ht ih =>
    obtain ⟨c, hi, hz⟩ := column_for_bit i b hb
    obtain ⟨cs, his, hzs⟩ := ih
    exact ⟨c :: cs, by simp only [List.map_cons, hi, his],
      by simp only [List.map_cons, hz, hzs]⟩

theorem legal_extrema_bits : ∀ i : Input,
    allowed (inputMust i) (inputMay i) (inputMust i) = true ∧
    allowed (inputMust i) (inputMay i) (inputMay i) = true ∧
    allowed (inputMust i) (inputMay i) (inputSeed i) = true := by decide

theorem extrema_admissible (is : List Input) :
    AdmissibleBits is (is.map inputMust) ∧ AdmissibleBits is (is.map inputMay) ∧
    AdmissibleBits is (is.map inputSeed) := by
  induction is with
  | nil => exact ⟨.nil, .nil, .nil⟩
  | cons i rest ih =>
    have h := legal_extrema_bits i
    exact ⟨.cons h.1 ih.1, .cons h.2.1 ih.2.1, .cons h.2.2 ih.2.2⟩

theorem digit_limits : ∀ (i : Input) (b : Bool),
    allowed (inputMust i) (inputMay i) b = true →
    digit (inputMust i) ≤ digit b ∧ digit b ≤ digit (inputMay i) := by decide

theorem mask_limits {is : List Input} {bs : List Bool} (h : AdmissibleBits is bs) :
    value (is.map inputMust) ≤ value bs ∧ value bs ≤ value (is.map inputMay) := by
  induction h with
  | nil => exact ⟨Nat.le_refl 0, Nat.le_refl 0⟩
  | @cons i b rest tail hb ht ih =>
    have hd := digit_limits i b hb
    simp only [List.map_cons, value]
    exact ⟨Nat.add_le_add hd.1 (Nat.mul_le_mul_left 2 ih.1),
      Nat.add_le_add hd.2 (Nat.mul_le_mul_left 2 ih.2)⟩

theorem masked_extrema (is : List Input) :
    Masked is (value (is.map inputMust)) ∧ Masked is (value (is.map inputMay)) ∧
    (∀ z, Masked is z → value (is.map inputMust) ≤ z ∧ z ≤ value (is.map inputMay)) := by
  have h := extrema_admissible is
  refine ⟨⟨is.map inputMust, h.1, rfl⟩, ⟨is.map inputMay, h.2.1, rfl⟩, ?_⟩
  intro z hz
  obtain ⟨bs, hb, rfl⟩ := hz
  exact mask_limits hb

theorem greater_exists_iff (is : List Input) :
    (∃ z, Masked is z ∧ value (is.map inputSeed) < z) ↔
      value (is.map inputSeed) ≠ value (is.map inputMay) := by
  have bounds := mask_limits (extrema_admissible is).2.2
  have extrema := masked_extrema is
  constructor
  · rintro ⟨z, hz, hg⟩
    have upper := (extrema.2.2 z hz).2
    omega
  · intro hn
    exact ⟨value (is.map inputMay), extrema.2.1, by omega⟩

theorem trace_admissible (m : Machine n) (xs : List Column) (s : Fin n)
    (hl : (trace m s xs).all (fun e => !(e .must) || e .output) = true)
    (hu : (trace m s xs).all (fun e => !(e .output) || e .may) = true) :
    AdmissibleBits (xs.map project) (emitted m s (xs.map project)) := by
  induction xs generalizing s with
  | nil => exact .nil
  | cons c rest ih =>
    simp only [trace, List.all_cons, Bool.and_eq_true, environment] at hl hu
    apply AdmissibleBits.cons
    · simp only [allowed, project_must, project_may, Bool.and_eq_true]
      exact ⟨hl.1, by simpa only [Bool.or_comm] using hu.1⟩
    · exact ih _ hl.2 hu.2

/- The endpoint uses the whole legal numerical carrier, not a chosen competitor.
All three clauses are present: membership, strict least greater, exact wrap. -/
def CyclicSuccessor (is : List Input) (y : Nat) : Prop :=
  Masked is y ∧
  ((∃ z, Masked is z ∧ value (is.map inputSeed) < z) →
    value (is.map inputSeed) < y ∧
      ∀ z, Masked is z → value (is.map inputSeed) < z → y ≤ z) ∧
  ((¬ ∃ z, Masked is z ∧ value (is.map inputSeed) < z) → y = value (is.map inputMust))

theorem exact_cyclic_successor (m : Machine n) (cert : Certificate n k)
    (accepted : Accepted m successorProgram cert) (is : List Input) (positive : 0 < is.length) :
    CyclicSuccessor is (value (emitted m m.initial is)) := by
  obtain ⟨cs, hc, _⟩ := encode_columns (extrema_admissible is).1
  have nonempty : 0 < cs.length := by
    have lengths : cs.length = is.length := by
      simpa only [List.length_map] using congrArg List.length hc
    rw [lengths]
    exact positive
  obtain ⟨hl, hu, hg, hm, hw⟩ := cyclic_successor_all_widths m cert accepted cs nonempty
  have member := trace_admissible m cs m.initial
    (by simpa only [subsetBits, execute_history, bitEval] using hl)
    (by simpa only [subsetBits, execute_history, bitEval] using hu)
  have greater : value (is.map inputSeed) ≠ value (is.map inputMay) →
      value (is.map inputSeed) < value (emitted m m.initial is) := by
    simpa only [number_seed, number_may, number_output, hc] using hg
  have wrap : value (is.map inputSeed) = value (is.map inputMay) →
      value (emitted m m.initial is) = value (is.map inputMust) := by
    simpa only [number_seed, number_may, number_output, number_must, hc] using hw
  refine cyclic_extrema_characterization (Masked is)
    (value (is.map inputMust)) (value (is.map inputMay))
    (value (is.map inputSeed)) (value (emitted m m.initial is))
    ⟨is.map inputSeed, (extrema_admissible is).2.2, rfl⟩
    (masked_extrema is).2.1
    (fun z hz => ((masked_extrema is).2.2 z hz).2)
    ⟨emitted m m.initial is, by simpa only [hc] using member, rfl⟩ greater ?_ wrap
  intro z hz hgz
  obtain ⟨bs, hb, hv⟩ := hz
  obtain ⟨zs, hi, ha⟩ := encode_columns hb
  have nz : 0 < zs.length := by
    have lengths : zs.length = is.length := by
      simpa only [List.length_map] using congrArg List.length hi
    rw [lengths]
    exact positive
  have hzpost := (cyclic_successor_all_widths m cert accepted zs nz).2.2.2.1
  have hmz : value (is.map inputSeed) < z → value (emitted m m.initial is) ≤ z := by
    simpa only [number_seed, number_alternative, number_output, hi, ha, hv] using hzpost
  exact hmz hgz

theorem original_exact (is : List Input) (positive : 0 < is.length) :
    CyclicSuccessor is (value (emitted Original.machine Original.machine.initial is)) := by
  apply exact_cyclic_successor Original.machine Original.certificate _ is positive
  simpa only [Original.program_matches] using Original.accepted

theorem irrelevant_exact (is : List Input) (positive : 0 < is.length) :
    CyclicSuccessor is (value (emitted Irrelevant.machine Irrelevant.machine.initial is)) := by
  apply exact_cyclic_successor Irrelevant.machine Irrelevant.certificate _ is positive
  simpa only [Irrelevant.program_matches] using Irrelevant.accepted

theorem cyclic_successor_unique (is : List Input) {y z : Nat}
    (hy : CyclicSuccessor is y) (hz : CyclicSuccessor is z) : y = z := by
  by_cases h : value (is.map inputSeed) = value (is.map inputMay)
  · have none : ¬ ∃ x, Masked is x ∧ value (is.map inputSeed) < x := by
      rintro ⟨x, hx, hg⟩
      have upper := (masked_extrema is).2.2 x hx
      omega
    exact (hy.2.2 none).trans (hz.2.2 none).symm
  · have greater := (greater_exists_iff is).mpr h
    exact Nat.le_antisymm ((hy.2.1 greater).2 z hz.1 (hz.2.1 greater).1)
      ((hz.2.1 greater).2 y hy.1 (hy.2.1 greater).1)

theorem original_irrelevant_same (is : List Input) (positive : 0 < is.length) :
    value (emitted Original.machine Original.machine.initial is) =
      value (emitted Irrelevant.machine Irrelevant.machine.initial is) :=
  cyclic_successor_unique is (original_exact is positive) (irrelevant_exact is positive)

end QKFTarget.MaskedWords
