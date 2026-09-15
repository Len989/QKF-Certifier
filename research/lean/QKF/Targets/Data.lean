import QKF.Targets.Kernel

/- Generated DATA from independently replayed run-2 packages.
The source frontend and this translation are outside the Lean theorem. -/
namespace QKF.Targets.Data

def originalMachine : Machine 2 where
  initial := 0
  step := fun q a => match q.val, a.val with
    | 0, 0 => (false, 0)
    | 0, 1 => (true, 1)
    | 0, 2 => (false, 0)
    | 0, 3 => (true, 0)
    | 1, 0 => (false, 1)
    | 1, 1 => (false, 1)
    | 1, 2 => (true, 1)
    | _, _ => (true, 1)

def originalProgram : Program 7 where
  atoms := fun i => match i.val with
    | 0 => ⟨.subset, (.var .must), (.var .output)⟩
    | 1 => ⟨.subset, (.var .output), (.var .may)⟩
    | 2 => ⟨.eq, (.var .seed), (.var .may)⟩
    | 3 => ⟨.order, (.var .seed), (.var .output)⟩
    | 4 => ⟨.order, (.var .seed), (.var .alternative)⟩
    | 5 => ⟨.order, (.var .output), (.var .alternative)⟩
    | _ => ⟨.eq, (.var .output), (.var .must)⟩
  precondition := (.literal true)
  obligation := (.conj (.query 0) (.conj (.query 1) (.conj (.implies (.neg (.query 2)) (.ult 3)) (.conj (.implies (.ult 4) (.ule 5)) (.conj (.implies (.query 2) (.query 6)) (.literal true))))))

def originalCertificate : Certificate 7 2 9 where
  initial := 0
  states := fun i => match i.val with
    | 0 => ⟨0, false, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .eq), (.ordering .eq), (.ordering .eq), (.boolean true)].getD j.val (.boolean false)⟩
    | 1 => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .eq), (.ordering .eq), (.ordering .eq), (.boolean true)].getD j.val (.boolean false)⟩
    | 2 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .eq), (.ordering .gt), (.boolean false)].getD j.val (.boolean false)⟩
    | 3 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .lt), (.ordering .eq), (.boolean false)].getD j.val (.boolean false)⟩
    | 4 => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .gt), (.ordering .gt), (.ordering .eq), (.boolean true)].getD j.val (.boolean false)⟩
    | 5 => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .gt), (.ordering .eq), (.ordering .lt), (.boolean true)].getD j.val (.boolean false)⟩
    | 6 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .lt), (.ordering .lt), (.boolean false)].getD j.val (.boolean false)⟩
    | 7 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .gt), (.ordering .gt), (.boolean false)].getD j.val (.boolean false)⟩
    | _ => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .gt), (.ordering .gt), (.ordering .lt), (.boolean true)].getD j.val (.boolean false)⟩
  edges := fun i c => match i.val with
    | 0 => ([1, 2, 3, 4, 5, 1] : List (Fin 9)).getD c.val 0
    | 1 => ([1, 2, 3, 4, 5, 1] : List (Fin 9)).getD c.val 0
    | 2 => ([2, 2, 6, 7, 2, 2] : List (Fin 9)).getD c.val 0
    | 3 => ([3, 3, 6, 7, 3, 3] : List (Fin 9)).getD c.val 0
    | 4 => ([4, 7, 3, 4, 8, 4] : List (Fin 9)).getD c.val 0
    | 5 => ([5, 2, 6, 8, 5, 5] : List (Fin 9)).getD c.val 0
    | 6 => ([6, 6, 6, 7, 6, 6] : List (Fin 9)).getD c.val 0
    | 7 => ([7, 7, 6, 7, 7, 7] : List (Fin 9)).getD c.val 0
    | _ => ([8, 7, 6, 8, 8, 8] : List (Fin 9)).getD c.val 0

def irrelevantMachine : Machine 2 where
  initial := 0
  step := fun q a => match q.val, a.val with
    | 0, 0 => (false, 0)
    | 0, 1 => (true, 1)
    | 0, 2 => (false, 0)
    | 0, 3 => (true, 0)
    | 1, 0 => (false, 1)
    | 1, 1 => (false, 1)
    | 1, 2 => (true, 1)
    | _, _ => (true, 1)

def irrelevantProgram : Program 7 where
  atoms := fun i => match i.val with
    | 0 => ⟨.subset, (.var .must), (.var .output)⟩
    | 1 => ⟨.subset, (.var .output), (.var .may)⟩
    | 2 => ⟨.eq, (.var .seed), (.var .may)⟩
    | 3 => ⟨.order, (.var .seed), (.var .output)⟩
    | 4 => ⟨.order, (.var .seed), (.var .alternative)⟩
    | 5 => ⟨.order, (.var .output), (.var .alternative)⟩
    | _ => ⟨.eq, (.var .output), (.var .must)⟩
  precondition := (.literal true)
  obligation := (.conj (.query 0) (.conj (.query 1) (.conj (.implies (.neg (.query 2)) (.ult 3)) (.conj (.implies (.ult 4) (.ule 5)) (.conj (.implies (.query 2) (.query 6)) (.literal true))))))

def irrelevantCertificate : Certificate 7 2 9 where
  initial := 0
  states := fun i => match i.val with
    | 0 => ⟨0, false, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .eq), (.ordering .eq), (.ordering .eq), (.boolean true)].getD j.val (.boolean false)⟩
    | 1 => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .eq), (.ordering .eq), (.ordering .eq), (.boolean true)].getD j.val (.boolean false)⟩
    | 2 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .eq), (.ordering .gt), (.boolean false)].getD j.val (.boolean false)⟩
    | 3 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .lt), (.ordering .eq), (.boolean false)].getD j.val (.boolean false)⟩
    | 4 => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .gt), (.ordering .gt), (.ordering .eq), (.boolean true)].getD j.val (.boolean false)⟩
    | 5 => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .gt), (.ordering .eq), (.ordering .lt), (.boolean true)].getD j.val (.boolean false)⟩
    | 6 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .lt), (.ordering .lt), (.boolean false)].getD j.val (.boolean false)⟩
    | 7 => ⟨1, true, fun j => [(.boolean true), (.boolean true), (.boolean false), (.ordering .lt), (.ordering .gt), (.ordering .gt), (.boolean false)].getD j.val (.boolean false)⟩
    | _ => ⟨0, true, fun j => [(.boolean true), (.boolean true), (.boolean true), (.ordering .gt), (.ordering .gt), (.ordering .lt), (.boolean true)].getD j.val (.boolean false)⟩
  edges := fun i c => match i.val with
    | 0 => ([1, 2, 3, 4, 5, 1] : List (Fin 9)).getD c.val 0
    | 1 => ([1, 2, 3, 4, 5, 1] : List (Fin 9)).getD c.val 0
    | 2 => ([2, 2, 6, 7, 2, 2] : List (Fin 9)).getD c.val 0
    | 3 => ([3, 3, 6, 7, 3, 3] : List (Fin 9)).getD c.val 0
    | 4 => ([4, 7, 3, 4, 8, 4] : List (Fin 9)).getD c.val 0
    | 5 => ([5, 2, 6, 8, 5, 5] : List (Fin 9)).getD c.val 0
    | 6 => ([6, 6, 6, 7, 6, 6] : List (Fin 9)).getD c.val 0
    | 7 => ([7, 7, 6, 7, 7, 7] : List (Fin 9)).getD c.val 0
    | _ => ([8, 7, 6, 8, 8, 8] : List (Fin 9)).getD c.val 0

end QKF.Targets.Data
