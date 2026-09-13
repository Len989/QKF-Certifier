import QKF.RowRules

namespace QKF

inductive Order3 | lt | eq | gt deriving DecidableEq, Repr

def bitCmp (a b : Bool) : Order3 :=
  if a == b then .eq else if a then .gt else .lt
def prepend (a b : Bool) (suffix : Order3) : Order3 :=
  match bitCmp a b with | .eq => suffix | r => r
def bxor (a b : Bool) : Bool := if a then !b else b

abbrev Column := Fin 6
def mustBit (c : Column) : Bool := c.val == 5
def mayBit (c : Column) : Bool := c.val != 0
def inputBit (c : Column) : Bool := c.val == 3 || c.val == 4 || c.val == 5
def candidateBit (c : Column) : Bool := c.val == 2 || c.val == 4 || c.val == 5
def optionalBit (c : Column) : Bool := mayBit c && !mustBit c
def allowed (must may value : Bool) : Bool := (!must || value) && (may || !value)

theorem column_legal : ∀ c : Column,
    allowed (mustBit c) (mayBit c) (inputBit c) = true ∧
    allowed (mustBit c) (mayBit c) (candidateBit c) = true := by decide

theorem columns_exhaustive : ∀ must may g x : Bool,
    allowed must may g = true → allowed must may x = true →
    ∃ c : Column, mustBit c = must ∧ mayBit c = may ∧
      inputBit c = g ∧ candidateBit c = x := by
  intro must may g x hg hx
  cases must <;> cases may <;> cases g <;> cases x <;> simp_all [allowed]
  all_goals first
    | exact ⟨0, by decide⟩
    | exact ⟨1, by decide⟩
    | exact ⟨2, by decide⟩
    | exact ⟨3, by decide⟩
    | exact ⟨4, by decide⟩
    | exact ⟨5, by decide⟩

def nativeStep (c : Column) (carry : Bool) : Bool × Bool :=
  if optionalBit c then (bxor (inputBit c) carry, inputBit c && carry)
  else (inputBit c, carry)

inductive Phase | before | clear | carry deriving DecidableEq, Repr
def started : Phase → Bool | .before => false | _ => true
def physicalCarry : Phase → Bool | .carry => true | _ => false
def phaseObservation : Phase → Bool | .clear => false | _ => true

/- Literal one-cell semantics of the guarded add/OR repair, with the incoming
physical carry exposed. Java parsing and word-to-JVM translation are not
asserted as theorems by this pilot. -/
def sourceCell (phase : Phase) (c : Column) : Bool × Phase :=
  let g := inputBit c
  let incoming := physicalCarry phase
  let bit := bxor g incoming
  let outgoing := g && incoming
  if started phase then
    let restored := if mustBit c && !bit then true else bit
    if !mayBit c && restored then (false, .carry)
    else (restored, if outgoing then .carry else .clear)
  else if optionalBit c then (bxor g true, if g then .carry else .clear)
  else (g, .before)

theorem source_phase_factor : ∀ (p : Phase) (c : Column),
    ((sourceCell p c).1, phaseObservation (sourceCell p c).2) =
      nativeStep c (phaseObservation p) := by
  intro p
  cases p <;> decide

theorem native_cell_membership : ∀ (c : Column) (carry : Bool),
    allowed (mustBit c) (mayBit c) (nativeStep c carry).1 = true := by decide

def decodeCarrier (n : Fin 4) : Carrier := (n.val % 2 == 1, n.val / 2 == 1)
def encodeCarrier (p : Carrier) : Fin 4 :=
  if p.2 then (if p.1 then 3 else 2) else (if p.1 then 1 else 0)
def atomCode (b : Bool) : Fin 4 := if b then 2 else 1

def labelIndex (c : Column) (output : Bool) : Fin 8 :=
  if c.val == 0 then (if output then 1 else 0)
  else if c.val == 5 then (if output then 7 else 6)
  else if inputBit c then (if output then 5 else 4)
  else (if output then 3 else 2)

def labelColumn (label : Fin 8) : Column :=
  if label.val < 2 then 0 else if label.val < 4 then 1
  else if label.val < 6 then 3 else 5
def labelOutput (label : Fin 8) : Bool := label.val % 2 == 1

def nativeRow (label : Fin 8) (p : Carrier) : Carrier :=
  let step := nativeStep (labelColumn label)
  (((step false).1 == labelOutput label) && mem p (step false).2,
   ((step true).1 == labelOutput label) && mem p (step true).2)

abbrev RowTables := Fin 8 → Fin 4 → Fin 4
def completedRow (tables : RowTables) (label : Fin 8) (p : Carrier) : Carrier :=
  decodeCarrier (tables label (encodeCarrier p))

def rowAllows (tables : RowTables) (c : Column) (output next carry : Bool) : Bool :=
  mem (decodeCarrier (tables (labelIndex c output) (atomCode next))) carry

/- The actual transition consumes the supplied/forced row table. -/
def stepFromRows (tables : RowTables) (c : Column) (carry : Bool) : Bool × Bool :=
  if rowAllows tables c false false carry then (false, false)
  else if rowAllows tables c false true carry then (false, true)
  else if rowAllows tables c true false carry then (true, false)
  else (true, true)

structure Observation where
  carry : Bool
  gx : Order3
  tx : Order3
  gt : Order3
  gmax : Bool
  tmin : Bool
  seen : Bool
  deriving DecidableEq, Repr

def start : Observation := ⟨true, .eq, .eq, .eq, true, true, false⟩

def transition (tables : RowTables) (q : Observation) (c : Column) : Observation :=
  let action := stepFromRows tables c q.carry
  ⟨action.2, prepend (inputBit c) (candidateBit c) q.gx,
    prepend action.1 (candidateBit c) q.tx, prepend (inputBit c) action.1 q.gt,
    q.gmax && (inputBit c == mayBit c), q.tmin && (action.1 == mustBit c),
    q.seen || optionalBit c⟩

abbrev SignMask := Fin 3
def signMust (s : SignMask) : Bool := s.val == 2
def signMay (s : SignMask) : Bool := s.val != 0

def boundaryGood (q : Observation) : Prop :=
  ∀ (s : SignMask) (xs : Bool), allowed (signMust s) (signMay s) xs = true →
    let gs := signMay s
    let ts := bxor gs q.carry
    prepend (!gs) (!xs) q.gx = .lt →
      !(q.carry && !gs) = true ∧
      allowed (signMust s) (signMay s) ts = true ∧
      prepend (!gs) (!ts) q.gt = .lt ∧
      prepend (!ts) (!xs) q.tx ≠ .gt

end QKF
