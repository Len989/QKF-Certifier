import QKFTarget.Masked

/-! Conditional composition of a floor and a cyclic successor.
The floor contract is an explicit hypothesis, not an assumed checked theorem
about the descending Java code. This semantic wrapper is not a JSON interpreter.
No finite order enumeration is needed for the generic order argument. -/
namespace QKFTarget.Ceiling

/-- A genuine maximum of the legal elements at most the bound. -/
def FloorContract (L : Nat → Prop) (bound result : Nat) : Prop :=
  L result ∧ result ≤ bound ∧ ∀ z, L z → z ≤ bound → z ≤ result

/-- The full cyclic contract, including membership and exact wrap. -/
def SuccessorContract (L : Nat → Prop) (minimum seed result : Nat) : Prop :=
  L result ∧
  ((∃ z, L z ∧ seed < z) → seed < result ∧ ∀ z, L z → seed < z → result ≤ z) ∧
  ((¬ ∃ z, L z ∧ seed < z) → result = minimum)

/-- None and Some 0 are different outcomes. The empty clause is exact. -/
def ExactCeiling (L : Nat → Prop) (bound : Nat) : Option Nat → Prop
  | none => ∀ z, L z → z < bound
  | some y => L y ∧ bound ≤ y ∧ ∀ z, L z → bound ≤ z → y ≤ z

/-- The published wrapper's branch structure, at the numerical semantic level. -/
def compose (minimum maximum bound : Nat) (floor next : Nat → Nat) : Option Nat :=
  if bound < minimum then some minimum
  else if maximum < bound then none
  else let g := floor bound
       if g = bound then some g else some (next g)

/-- The later successor also instantiates the earlier universal floor contract. -/
theorem floor_then_successor (L : Nat → Prop) (minimum maximum bound g y : Nat)
    (maximum_legal : L maximum) (bound_below : bound ≤ maximum)
    (floor_ok : FloorContract L bound g) (gap : g < bound)
    (next_ok : SuccessorContract L minimum g y) : ExactCeiling L bound (some y) := by
  have greater : ∃ z, L z ∧ g < z :=
    ⟨maximum, maximum_legal, Nat.lt_of_lt_of_le gap bound_below⟩
  have advance := next_ok.2.1 greater
  have above : bound < y := by
    have impossible : ¬ y ≤ bound := by
      intro hy
      exact (Nat.not_le_of_lt advance.1) (floor_ok.2.2 y next_ok.1 hy)
    exact Nat.lt_of_not_ge impossible
  exact ⟨next_ok.1, Nat.le_of_lt above,
    fun z hz hb => advance.2 z hz (Nat.lt_of_lt_of_le gap hb)⟩

theorem compose_correct (L : Nat → Prop) (minimum maximum : Nat)
    (minimum_legal : L minimum) (maximum_legal : L maximum)
    (limits : ∀ z, L z → minimum ≤ z ∧ z ≤ maximum)
    (floor next : Nat → Nat)
    (floor_ok : ∀ b, minimum ≤ b → b ≤ maximum → FloorContract L b (floor b))
    (next_ok : ∀ g, L g → SuccessorContract L minimum g (next g)) (bound : Nat) :
    ExactCeiling L bound (compose minimum maximum bound floor next) := by
  by_cases below : bound < minimum
  · simp only [compose, if_pos below, ExactCeiling]
    exact ⟨minimum_legal, Nat.le_of_lt below, fun z hz _ => (limits z hz).1⟩
  · by_cases above : maximum < bound
    · simp only [compose, if_neg below, if_pos above, ExactCeiling]
      exact fun z hz => Nat.lt_of_le_of_lt (limits z hz).2 above
    · have lower : minimum ≤ bound := Nat.le_of_not_gt below
      have upper : bound ≤ maximum := Nat.le_of_not_gt above
      have hf := floor_ok bound lower upper
      by_cases hit : floor bound = bound
      · simp only [compose, if_neg below, if_neg above, if_pos hit, ExactCeiling]
        exact ⟨hf.1, Nat.le_of_eq hit.symm, fun z _ hz => Nat.le_trans (Nat.le_of_eq hit) hz⟩
      · simp only [compose, if_neg below, if_neg above, if_neg hit]
        have gap : floor bound < bound := (Nat.lt_iff_le_and_ne).mpr ⟨hf.2.1, hit⟩
        exact floor_then_successor L minimum maximum bound (floor bound) (next (floor bound))
          maximum_legal upper hf gap (next_ok (floor bound) hf.1)

theorem empty_iff_no_candidate (L : Nat → Prop) (bound : Nat) (r : Option Nat)
    (h : ExactCeiling L bound r) : r = none ↔ ¬ ∃ z, L z ∧ bound ≤ z := by
  cases r with
  | none =>
    constructor
    · intro _ hex
      obtain ⟨z, hz, hb⟩ := hex
      exact (Nat.not_le_of_lt (h z hz)) hb
    · intro _; rfl
  | some y =>
    constructor
    · intro impossible; cases impossible
    · intro none
      exact False.elim (none ⟨y, h.1, h.2.1⟩)

theorem exact_ceiling_unique (L : Nat → Prop) (bound : Nat) (r s : Option Nat)
    (hr : ExactCeiling L bound r) (hs : ExactCeiling L bound s) : r = s := by
  cases r with
  | none =>
    cases s with
    | none => rfl
    | some y => exact False.elim ((Nat.not_le_of_lt (hr y hs.1)) hs.2.1)
  | some x =>
    cases s with
    | none => exact False.elim ((Nat.not_le_of_lt (hs x hr.1)) hr.2.1)
    | some y =>
      exact congrArg some (Nat.le_antisymm (hr.2.2 y hs.1 hs.2.1) (hs.2.2 x hr.1 hr.2.1))

end QKFTarget.Ceiling

namespace QKFTarget.MaskedWords

/- Mask identities are proved over the existing equally long bit-list carrier.
No unproved identification with Nat.land or machine Java longs is used. -/

def SameMasks (is js : List Input) : Prop :=
  is.map inputMust = js.map inputMust ∧ is.map inputMay = js.map inputMay

theorem admissible_same_masks {is js : List Input} (same : SameMasks is js) (bs : List Bool) :
    AdmissibleBits is bs ↔ AdmissibleBits js bs := by
  induction is generalizing js bs with
  | nil =>
    cases js with
    | nil => exact Iff.rfl
    | cons j js => cases same.1
  | cons i is ih =>
    cases js with
    | nil => cases same.1
    | cons j js =>
      have hm := List.cons.inj same.1
      have ha := List.cons.inj same.2
      cases bs with
      | nil => constructor <;> intro h <;> cases h
      | cons b bs =>
        constructor
        · intro h
          cases h with
          | cons hb ht =>
            exact .cons (by simpa only [hm.1, ha.1] using hb) ((ih ⟨hm.2, ha.2⟩ bs).mp ht)
        · intro h
          cases h with
          | cons hb ht =>
            exact .cons (by simpa only [hm.1, ha.1] using hb) ((ih ⟨hm.2, ha.2⟩ bs).mpr ht)

theorem masked_same_masks {is js : List Input} (same : SameMasks is js) (z : Nat) :
    Masked is z ↔ Masked js z := by
  constructor
  · rintro ⟨bs, hb, hv⟩
    exact ⟨bs, (admissible_same_masks same bs).mp hb, hv⟩
  · rintro ⟨bs, hb, hv⟩
    exact ⟨bs, (admissible_same_masks same bs).mpr hb, hv⟩

/-- Retain both masks; replace only the seed by a legal bit. -/
def withSeed (i : Input) (b : Bool) : Input :=
  if inputMust i then 3 else if inputMay i then (if b then 2 else 1) else 0

theorem withSeed_facts : ∀ (i : Input) (b : Bool),
    inputMust (withSeed i b) = inputMust i ∧ inputMay (withSeed i b) = inputMay i ∧
    (allowed (inputMust i) (inputMay i) b = true → inputSeed (withSeed i b) = b) := by decide

def reseed : List Input → List Bool → List Input
  | i :: is, b :: bs => withSeed i b :: reseed is bs
  | _, _ => []

theorem reseed_facts {is : List Input} {bs : List Bool} (h : AdmissibleBits is bs) :
    SameMasks (reseed is bs) is ∧ (reseed is bs).map inputSeed = bs ∧
      (reseed is bs).length = is.length := by
  induction h with
  | nil => exact ⟨⟨rfl, rfl⟩, rfl, rfl⟩
  | @cons i b is bs hb ht ih =>
    have f := withSeed_facts i b
    refine ⟨⟨?_, ?_⟩, ?_, ?_⟩
    · simp only [reseed, List.map_cons, f.1, ih.1.1]
    · simp only [reseed, List.map_cons, f.2.1, ih.1.2]
    · simp only [reseed, List.map_cons, f.2.2 hb, ih.2.1]
    · simp only [reseed, List.length_cons, ih.2.2]

/-- Canonical width-limited bits, without a choice of witness representation. -/
def bitsOf : Nat → Nat → List Bool
  | 0, _ => []
  | w + 1, z => (z % 2 == 1) :: bitsOf w (z / 2)

theorem bitsOf_value (bs : List Bool) : bitsOf bs.length (value bs) = bs := by
  induction bs with
  | nil => rfl
  | cons b bs ih =>
    have div : (digit b + 2 * value bs) / 2 = value bs := by
      clear ih
      have d : digit b < 2 := by cases b <;> decide
      omega
    have rem : (digit b + 2 * value bs) % 2 = digit b := by
      clear ih div
      have d : digit b < 2 := by cases b <;> decide
      omega
    have flag : (digit b == 1) = b := by cases b <;> decide
    simp only [List.length_cons, value, bitsOf, rem, flag, div, ih]

theorem bitsOf_masked {is : List Input} {z : Nat} (h : Masked is z) :
    AdmissibleBits is (bitsOf is.length z) ∧ value (bitsOf is.length z) = z := by
  obtain ⟨bs, hb, rfl⟩ := h
  have eq : bitsOf is.length (value bs) = bs := by
    rw [← admissible_length hb, bitsOf_value]
  rw [eq]
  exact ⟨hb, rfl⟩

/- Descending optional-bit extensions have exactly the same numerical carrier. -/
inductive OptionalBits : List Input → List Bool → Prop where
  | nil : OptionalBits [] []
  | cons {i : Input} {b : Bool} {is : List Input} {bs : List Bool} :
      (!b || (inputMay i && !inputMust i)) = true → OptionalBits is bs →
        OptionalBits (i :: is) (b :: bs)

def fillOptional : List Input → List Bool → List Bool
  | i :: is, b :: bs => (inputMust i || b) :: fillOptional is bs
  | _, _ => []

def optionalPart : List Input → List Bool → List Bool
  | i :: is, b :: bs => (b && !inputMust i) :: optionalPart is bs
  | _, _ => []

def Extensions (is : List Input) (z : Nat) : Prop :=
  ∃ bs, OptionalBits is bs ∧ value (fillOptional is bs) = z

theorem optional_bit_decompose : ∀ (i : Input) (b : Bool),
    allowed (inputMust i) (inputMay i) b = true →
    (!(b && !inputMust i) || (inputMay i && !inputMust i)) = true ∧
      (inputMust i || (b && !inputMust i)) = b := by decide

theorem optional_bit_fill : ∀ (i : Input) (b : Bool),
    (!b || (inputMay i && !inputMust i)) = true →
    allowed (inputMust i) (inputMay i) (inputMust i || b) = true := by decide

theorem optional_decompose {is : List Input} {bs : List Bool} (h : AdmissibleBits is bs) :
    OptionalBits is (optionalPart is bs) ∧ fillOptional is (optionalPart is bs) = bs := by
  induction h with
  | nil => exact ⟨.nil, rfl⟩
  | @cons i b is bs hb ht ih =>
    have f := optional_bit_decompose i b hb
    refine ⟨.cons f.1 ih.1, ?_⟩
    simp only [optionalPart, fillOptional, f.2, ih.2]

theorem optional_fill_admissible {is : List Input} {bs : List Bool} (h : OptionalBits is bs) :
    AdmissibleBits is (fillOptional is bs) := by
  induction h with
  | nil => exact .nil
  | cons hb ht ih => exact .cons (optional_bit_fill _ _ hb) ih

theorem masked_iff_extensions (is : List Input) (z : Nat) : Masked is z ↔ Extensions is z := by
  constructor
  · rintro ⟨bs, hb, hv⟩
    have f := optional_decompose hb
    exact ⟨optionalPart is bs, f.1, (congrArg value f.2).trans hv⟩
  · rintro ⟨bs, hb, hv⟩
    exact ⟨fillOptional is bs, optional_fill_admissible hb, hv⟩

/-- Actual existing factor run, reseeded with the exact numerical floor result. -/
def nextFrom (m : Machine n) (is : List Input) (g : Nat) : Nat :=
  value (emitted m m.initial (reseed is (bitsOf is.length g)))

theorem nextFrom_correct (m : Machine n) (cert : Certificate n k)
    (accepted : Accepted m successorProgram cert) (is : List Input) (positive : 0 < is.length)
    (g : Nat) (legal : Masked is g) :
    Ceiling.SuccessorContract (Masked is) (value (is.map inputMust)) g (nextFrom m is g) := by
  have bits := bitsOf_masked legal
  have f := reseed_facts bits.1
  have pos : 0 < (reseed is (bitsOf is.length g)).length := by rw [f.2.2]; exact positive
  have h := exact_cyclic_successor m cert accepted _ pos
  simpa only [CyclicSuccessor, Ceiling.SuccessorContract, nextFrom,
    masked_same_masks f.1, f.1.1, f.2.1, bits.2] using h

/-- The floor hypothesis is still unproved for a concrete descending source.
All masks, seed transfer, extrema and the successor's full contract are derived. -/
theorem masked_compose_correct (m : Machine n) (cert : Certificate n k)
    (accepted : Accepted m successorProgram cert) (is : List Input) (positive : 0 < is.length)
    (floor : Nat → Nat)
    (floor_ok : ∀ b, value (is.map inputMust) ≤ b → b ≤ value (is.map inputMay) →
      Ceiling.FloorContract (Extensions is) b (floor b)) (bound : Nat) :
    Ceiling.ExactCeiling (Masked is) bound
      (Ceiling.compose (value (is.map inputMust)) (value (is.map inputMay)) bound floor (nextFrom m is)) := by
  have e := masked_extrema is
  apply Ceiling.compose_correct (Masked is) _ _ e.1 e.2.1 e.2.2 floor (nextFrom m is)
  · intro b lo hi
    have h := floor_ok b lo hi
    exact ⟨(masked_iff_extensions is _).mpr h.1, h.2.1,
      fun z hz hb => h.2.2 z ((masked_iff_extensions is z).mp hz) hb⟩
  · exact fun g hg => nextFrom_correct m cert accepted is positive g hg

theorem original_ceiling (is : List Input) (positive : 0 < is.length) (floor : Nat → Nat)
    (floor_ok : ∀ b, value (is.map inputMust) ≤ b → b ≤ value (is.map inputMay) →
      Ceiling.FloorContract (Extensions is) b (floor b)) (bound : Nat) :
    Ceiling.ExactCeiling (Masked is) bound
      (Ceiling.compose (value (is.map inputMust)) (value (is.map inputMay)) bound floor
        (nextFrom Original.machine is)) := by
  apply masked_compose_correct Original.machine Original.certificate _ is positive floor floor_ok bound
  simpa only [Original.program_matches] using Original.accepted

theorem irrelevant_ceiling (is : List Input) (positive : 0 < is.length) (floor : Nat → Nat)
    (floor_ok : ∀ b, value (is.map inputMust) ≤ b → b ≤ value (is.map inputMay) →
      Ceiling.FloorContract (Extensions is) b (floor b)) (bound : Nat) :
    Ceiling.ExactCeiling (Masked is) bound
      (Ceiling.compose (value (is.map inputMust)) (value (is.map inputMay)) bound floor
        (nextFrom Irrelevant.machine is)) := by
  apply masked_compose_correct Irrelevant.machine Irrelevant.certificate _ is positive floor floor_ok bound
  simpa only [Irrelevant.program_matches] using Irrelevant.accepted

end QKFTarget.MaskedWords
