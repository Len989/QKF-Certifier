import QKFTarget.Ceiling

/-! Executable semantic controls, not substitutes for the universal theorems. -/
namespace QKFTarget.Ceiling.Controls
open QKFTarget.MaskedWords

def legal4 (z : Nat) : Prop := z = 0 ∨ z = 1 ∨ z = 4 ∨ z = 5

def floor4 (b : Nat) : Nat := if 5 ≤ b then 5 else if 4 ≤ b then 4 else if 1 ≤ b then 1 else 0

def next4 (g : Nat) : Nat := if g = 0 then 1 else if g = 1 then 4 else if g = 4 then 5 else 0

/-- A nontrivial universal witness for the conditional floor hypothesis. -/
theorem floor4_contract (b : Nat) : FloorContract legal4 b (floor4 b) := by
  unfold floor4
  split
  · rename_i h
    refine ⟨Or.inr (Or.inr (Or.inr rfl)), h, ?_⟩
    intro z hz _
    rcases hz with rfl | rfl | rfl | rfl <;> decide
  · rename_i h5
    split
    · rename_i h4
      refine ⟨Or.inr (Or.inr (Or.inl rfl)), h4, ?_⟩
      intro z hz hb
      rcases hz with rfl | rfl | rfl | rfl <;> omega
    · rename_i h4
      split
      · rename_i h1
        refine ⟨Or.inr (Or.inl rfl), h1, ?_⟩
        intro z hz hb
        rcases hz with rfl | rfl | rfl | rfl <;> omega
      · rename_i h1
        refine ⟨Or.inl rfl, Nat.zero_le b, ?_⟩
        intro z hz hb
        rcases hz with rfl | rfl | rfl | rfl <;> omega

/-- The exact successor hypotheses also have a concrete universal witness. -/
theorem next4_contract (g : Nat) (hg : legal4 g) : SuccessorContract legal4 0 g (next4 g) := by
  rcases hg with rfl | rfl | rfl | rfl
  · change SuccessorContract legal4 0 0 1
    refine ⟨Or.inr (Or.inl rfl), ?_, ?_⟩
    · intro _; refine ⟨by decide, ?_⟩
      intro z hz hz0; omega
    · intro h; exact False.elim (h ⟨1, Or.inr (Or.inl rfl), by decide⟩)
  · change SuccessorContract legal4 0 1 4
    refine ⟨Or.inr (Or.inr (Or.inl rfl)), ?_, ?_⟩
    · intro _; refine ⟨by decide, ?_⟩
      intro z hz hz1
      rcases hz with rfl | rfl | rfl | rfl <;> omega
    · intro h; exact False.elim (h ⟨4, Or.inr (Or.inr (Or.inl rfl)), by decide⟩)
  · change SuccessorContract legal4 0 4 5
    refine ⟨Or.inr (Or.inr (Or.inr rfl)), ?_, ?_⟩
    · intro _; refine ⟨by decide, ?_⟩
      intro z hz hz4
      rcases hz with rfl | rfl | rfl | rfl <;> omega
    · intro h; exact False.elim (h ⟨5, Or.inr (Or.inr (Or.inr rfl)), by decide⟩)
  · change SuccessorContract legal4 0 5 0
    refine ⟨Or.inl rfl, ?_, fun _ => rfl⟩
    rintro ⟨z, hz, hgt⟩
    rcases hz with rfl | rfl | rfl | rfl <;> omega

theorem four_element_example_all_bounds (b : Nat) :
    ExactCeiling legal4 b (compose 0 5 b floor4 next4) := by
  apply compose_correct legal4 0 5 (Or.inl rfl) (Or.inr (Or.inr (Or.inr rfl)))
  · intro z hz
    rcases hz with rfl | rfl | rfl | rfl <;> decide
  · exact fun b _ _ => floor4_contract b
  · exact next4_contract

/-- This check directly evaluates membership, lower bound and leastness. -/
def valid (xs : List Nat) (b : Nat) : Option Nat → Bool
  | none => xs.all (fun z => decide (z < b))
  | some y => xs.contains y && decide (b ≤ y) &&
      xs.all (fun z => decide (b ≤ z → y ≤ z))

def mask4 : List Input := [1, 0, 1]
def universe4 : List Nat := [0, 1, 4, 5]
def actualNext : Nat → Nat := nextFrom Original.machine mask4

def floorIsOnlyBounded : Bool := valid universe4 2 (compose 0 5 2 (fun _ => 0) actualNext)
def wrongSuccessorSeed : Bool := valid universe4 2 (compose 0 5 2 floor4 (fun _ => actualNext 0))
def differentSuccessorMasks : Bool :=
  valid universe4 2 (compose 0 5 2 floor4 (nextFrom Original.machine [1, 1, 1]))
def wrapWithoutUpperGuard : Bool := valid universe4 6 (some (actualNext (floor4 6)))
def emptyReturnedAsZero : Bool := valid universe4 6 (some 0)
def skipSuccessor : Bool := valid universe4 2 (some (floor4 2))
def changedRequiredMask : Bool := valid [1, 3] 2 (some (nextFrom Original.machine [1, 1] 1))
def optionalBitsOutsideMay : Bool := universe4.contains (value (fillOptional mask4 [false, true, false]))

def positiveExamples : Bool :=
  (compose 0 5 0 floor4 actualNext == some 0) &&
  (compose 0 5 1 floor4 actualNext == some 1) &&
  (compose 0 5 2 floor4 actualNext == some 4) &&
  (compose 0 5 5 floor4 actualNext == some 5) &&
  (compose 0 5 6 floor4 actualNext == none) &&
  (compose 5 5 0 (fun _ => 5) (fun _ => 5) == some 5) &&
  (compose 5 5 5 (fun _ => 5) (fun _ => 5) == some 5) &&
  (compose 5 5 6 (fun _ => 5) (fun _ => 5) == none) &&
  (compose 0 0 0 (fun _ => 0) (nextFrom Original.machine [0]) == some 0) &&
  (compose 0 0 1 (fun _ => 0) (nextFrom Original.machine [0]) == none) &&
  (List.range 8).all (fun b => valid universe4 b (compose 0 5 b floor4 actualNext))

theorem positive : positiveExamples = true := by decide

end QKFTarget.Ceiling.Controls
