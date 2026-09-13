import QKF.Core

/- Generated data only. Checked.lean supplies the proof. -/
namespace QKF.Data

def states (i : Fin 8) : Observation :=
  match i.val with
  | 0 => ⟨true, .eq, .eq, .eq, true, true, false⟩
  | 1 => ⟨false, .eq, .gt, .lt, false, false, true⟩
  | 2 => ⟨false, .lt, .eq, .lt, false, false, true⟩
  | 3 => ⟨true, .gt, .eq, .gt, true, true, true⟩
  | 4 => ⟨true, .eq, .lt, .gt, true, true, true⟩
  | 5 => ⟨false, .lt, .lt, .lt, false, false, true⟩
  | 6 => ⟨false, .gt, .gt, .lt, false, false, true⟩
  | _ => ⟨true, .gt, .lt, .gt, true, true, true⟩

def edges (i : Fin 8) (c : Column) : Fin 8 :=
  match i.val, c.val with
  | 0, 0 => 0
  | 0, 1 => 1
  | 0, 2 => 2
  | 0, 3 => 3
  | 0, 4 => 4
  | 0, 5 => 0
  | 1, 0 => 1
  | 1, 1 => 1
  | 1, 2 => 5
  | 1, 3 => 6
  | 1, 4 => 1
  | 1, 5 => 1
  | 2, 0 => 2
  | 2, 1 => 2
  | 2, 2 => 5
  | 2, 3 => 6
  | 2, 4 => 2
  | 2, 5 => 2
  | 3, 0 => 3
  | 3, 1 => 6
  | 3, 2 => 2
  | 3, 3 => 3
  | 3, 4 => 7
  | 3, 5 => 3
  | 4, 0 => 4
  | 4, 1 => 1
  | 4, 2 => 5
  | 4, 3 => 7
  | 4, 4 => 4
  | 4, 5 => 4
  | 5, 0 => 5
  | 5, 1 => 5
  | 5, 2 => 5
  | 5, 3 => 6
  | 5, 4 => 5
  | 5, 5 => 5
  | 6, 0 => 6
  | 6, 1 => 6
  | 6, 2 => 5
  | 6, 3 => 6
  | 6, 4 => 6
  | 6, 5 => 6
  | 7, 0 => 7
  | 7, 1 => 6
  | 7, 2 => 5
  | 7, 3 => 7
  | 7, 4 => 7
  | 7, 5 => 7
  | _, _ => 0

def rows (r : Fin 8) (p : Fin 4) : Fin 4 :=
  match r.val, p.val with
  | 0, 0 => 0
  | 0, 1 => 1
  | 0, 2 => 2
  | 0, 3 => 3
  | 1, 0 => 0
  | 1, 1 => 0
  | 1, 2 => 0
  | 1, 3 => 0
  | 2, 0 => 0
  | 2, 1 => 1
  | 2, 2 => 0
  | 2, 3 => 1
  | 3, 0 => 0
  | 3, 1 => 2
  | 3, 2 => 0
  | 3, 3 => 2
  | 4, 0 => 0
  | 4, 1 => 0
  | 4, 2 => 2
  | 4, 3 => 2
  | 5, 0 => 0
  | 5, 1 => 1
  | 5, 2 => 0
  | 5, 3 => 1
  | 6, 0 => 0
  | 6, 1 => 0
  | 6, 2 => 0
  | 6, 3 => 0
  | 7, 0 => 0
  | 7, 1 => 1
  | 7, 2 => 2
  | 7, 3 => 3
  | _, _ => 0

end QKF.Data
