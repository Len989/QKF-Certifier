import QKFTarget.Numeric

/- Generated from checked run-2 packages; no search or phases. -/
set_option maxRecDepth 8192
set_option maxHeartbeats 8000000
namespace QKFTarget

namespace Original

def program : Program :=
  { atoms := [
      ⟨.subset, (.var .must), (.var .output)⟩,
      ⟨.subset, (.var .output), (.var .may)⟩,
      ⟨.eq, (.var .seed), (.var .may)⟩,
      ⟨.order, (.var .seed), (.var .output)⟩,
      ⟨.order, (.var .seed), (.var .alternative)⟩,
      ⟨.order, (.var .output), (.var .alternative)⟩,
      ⟨.eq, (.var .output), (.var .must)⟩],
    premise := (.literal true),
    target := (.conj (.query 0) (.conj (.query 1) (.conj (.implies (.neg (.query 2)) (.lt 3)) (.conj (.implies (.lt 4) (.le 5)) (.implies (.query 2) (.query 6)))))) }

theorem program_matches : program = successorProgram := by decide

def machine : Machine 2 :=
  { initial := 0, cell := fun s a =>
      match s.val, a.val with
      | 0, 0 => (false, 0)
      | 0, 1 => (true, 1)
      | 0, 2 => (false, 0)
      | 0, 3 => (true, 0)
      | 1, 0 => (false, 1)
      | 1, 1 => (false, 1)
      | 1, 2 => (true, 1)
      | 1, 3 => (true, 1)
      | _, _ => (false, 0) }

def states (i : Fin 9) : Observation 2 :=
  match i.val with
  | 0 => ⟨0, false, [(.flag true), (.flag true), (.flag true), (.order .eq), (.order .eq), (.order .eq), (.flag true)]⟩
  | 1 => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .eq), (.order .eq), (.order .eq), (.flag true)]⟩
  | 2 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .eq), (.order .gt), (.flag false)]⟩
  | 3 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .lt), (.order .eq), (.flag false)]⟩
  | 4 => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .gt), (.order .gt), (.order .eq), (.flag true)]⟩
  | 5 => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .gt), (.order .eq), (.order .lt), (.flag true)]⟩
  | 6 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .lt), (.order .lt), (.flag false)]⟩
  | 7 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .gt), (.order .gt), (.flag false)]⟩
  | _ => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .gt), (.order .gt), (.order .lt), (.flag true)]⟩

def edges (i : Fin 9) (c : Column) : Fin 9 :=
  match i.val, c.val with
  | 0, 0 => 1
  | 0, 1 => 2
  | 0, 2 => 3
  | 0, 3 => 4
  | 0, 4 => 5
  | 0, 5 => 1
  | 1, 0 => 1
  | 1, 1 => 2
  | 1, 2 => 3
  | 1, 3 => 4
  | 1, 4 => 5
  | 1, 5 => 1
  | 2, 0 => 2
  | 2, 1 => 2
  | 2, 2 => 6
  | 2, 3 => 7
  | 2, 4 => 2
  | 2, 5 => 2
  | 3, 0 => 3
  | 3, 1 => 3
  | 3, 2 => 6
  | 3, 3 => 7
  | 3, 4 => 3
  | 3, 5 => 3
  | 4, 0 => 4
  | 4, 1 => 7
  | 4, 2 => 3
  | 4, 3 => 4
  | 4, 4 => 8
  | 4, 5 => 4
  | 5, 0 => 5
  | 5, 1 => 2
  | 5, 2 => 6
  | 5, 3 => 8
  | 5, 4 => 5
  | 5, 5 => 5
  | 6, 0 => 6
  | 6, 1 => 6
  | 6, 2 => 6
  | 6, 3 => 7
  | 6, 4 => 6
  | 6, 5 => 6
  | 7, 0 => 7
  | 7, 1 => 7
  | 7, 2 => 6
  | 7, 3 => 7
  | 7, 4 => 7
  | 7, 5 => 7
  | 8, 0 => 8
  | 8, 1 => 7
  | 8, 2 => 6
  | 8, 3 => 8
  | 8, 4 => 8
  | 8, 5 => 8
  | _, _ => 0

def certificate : Certificate 2 9 :=
  ⟨states, edges, 0⟩

theorem accepted : Accepted machine program certificate := by decide

theorem formula_all_lengths (xs : List Column) :
    good program (run (step machine program) (start machine program) xs) = true :=
  closed_certificate_sound machine program certificate accepted xs

theorem numerical_all_widths (xs : List Column) (positive : 0 < xs.length) :
    SuccessorNumeric (run (concreteStep machine) (concreteStart machine) xs).numbers := by
  apply cyclic_successor_all_widths machine certificate
  · simpa only [program_matches] using accepted
  · exact positive

end Original

namespace Irrelevant

def program : Program :=
  { atoms := [
      ⟨.subset, (.var .must), (.var .output)⟩,
      ⟨.subset, (.var .output), (.var .may)⟩,
      ⟨.eq, (.var .seed), (.var .may)⟩,
      ⟨.order, (.var .seed), (.var .output)⟩,
      ⟨.order, (.var .seed), (.var .alternative)⟩,
      ⟨.order, (.var .output), (.var .alternative)⟩,
      ⟨.eq, (.var .output), (.var .must)⟩],
    premise := (.literal true),
    target := (.conj (.query 0) (.conj (.query 1) (.conj (.implies (.neg (.query 2)) (.lt 3)) (.conj (.implies (.lt 4) (.le 5)) (.implies (.query 2) (.query 6)))))) }

theorem program_matches : program = successorProgram := by decide

def machine : Machine 2 :=
  { initial := 0, cell := fun s a =>
      match s.val, a.val with
      | 0, 0 => (false, 0)
      | 0, 1 => (true, 1)
      | 0, 2 => (false, 0)
      | 0, 3 => (true, 0)
      | 1, 0 => (false, 1)
      | 1, 1 => (false, 1)
      | 1, 2 => (true, 1)
      | 1, 3 => (true, 1)
      | _, _ => (false, 0) }

def states (i : Fin 9) : Observation 2 :=
  match i.val with
  | 0 => ⟨0, false, [(.flag true), (.flag true), (.flag true), (.order .eq), (.order .eq), (.order .eq), (.flag true)]⟩
  | 1 => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .eq), (.order .eq), (.order .eq), (.flag true)]⟩
  | 2 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .eq), (.order .gt), (.flag false)]⟩
  | 3 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .lt), (.order .eq), (.flag false)]⟩
  | 4 => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .gt), (.order .gt), (.order .eq), (.flag true)]⟩
  | 5 => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .gt), (.order .eq), (.order .lt), (.flag true)]⟩
  | 6 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .lt), (.order .lt), (.flag false)]⟩
  | 7 => ⟨1, true, [(.flag true), (.flag true), (.flag false), (.order .lt), (.order .gt), (.order .gt), (.flag false)]⟩
  | _ => ⟨0, true, [(.flag true), (.flag true), (.flag true), (.order .gt), (.order .gt), (.order .lt), (.flag true)]⟩

def edges (i : Fin 9) (c : Column) : Fin 9 :=
  match i.val, c.val with
  | 0, 0 => 1
  | 0, 1 => 2
  | 0, 2 => 3
  | 0, 3 => 4
  | 0, 4 => 5
  | 0, 5 => 1
  | 1, 0 => 1
  | 1, 1 => 2
  | 1, 2 => 3
  | 1, 3 => 4
  | 1, 4 => 5
  | 1, 5 => 1
  | 2, 0 => 2
  | 2, 1 => 2
  | 2, 2 => 6
  | 2, 3 => 7
  | 2, 4 => 2
  | 2, 5 => 2
  | 3, 0 => 3
  | 3, 1 => 3
  | 3, 2 => 6
  | 3, 3 => 7
  | 3, 4 => 3
  | 3, 5 => 3
  | 4, 0 => 4
  | 4, 1 => 7
  | 4, 2 => 3
  | 4, 3 => 4
  | 4, 4 => 8
  | 4, 5 => 4
  | 5, 0 => 5
  | 5, 1 => 2
  | 5, 2 => 6
  | 5, 3 => 8
  | 5, 4 => 5
  | 5, 5 => 5
  | 6, 0 => 6
  | 6, 1 => 6
  | 6, 2 => 6
  | 6, 3 => 7
  | 6, 4 => 6
  | 6, 5 => 6
  | 7, 0 => 7
  | 7, 1 => 7
  | 7, 2 => 6
  | 7, 3 => 7
  | 7, 4 => 7
  | 7, 5 => 7
  | 8, 0 => 8
  | 8, 1 => 7
  | 8, 2 => 6
  | 8, 3 => 8
  | 8, 4 => 8
  | 8, 5 => 8
  | _, _ => 0

def certificate : Certificate 2 9 :=
  ⟨states, edges, 0⟩

theorem accepted : Accepted machine program certificate := by decide

theorem formula_all_lengths (xs : List Column) :
    good program (run (step machine program) (start machine program) xs) = true :=
  closed_certificate_sound machine program certificate accepted xs

theorem numerical_all_widths (xs : List Column) (positive : 0 < xs.length) :
    SuccessorNumeric (run (concreteStep machine) (concreteStart machine) xs).numbers := by
  apply cyclic_successor_all_widths machine certificate
  · simpa only [program_matches] using accepted
  · exact positive

end Irrelevant

end QKFTarget
