import Ground

namespace QKFComposition
open QKFGround

/-- A ground proof retains its own term DAG, events, and auxiliary goals.
Premise indices refer only to the already admitted composition prefix. -/
structure Derivation where
  request : Request
  certificate : Certificate
  premises : List Nat
  via : Option Nat
  claim : Equation
  query : Nat
  deriving Repr

inductive Entry where
  | native (index : Nat)
  | derived (proof : Derivation)
  deriving Repr

structure Consumer where
  index : Nat
  claim : Equation
  deriving DecidableEq, Repr

structure Packet where
  sorts : Nat
  signature : Signature
  assumptions : List Equation
  entries : List Entry
  consumers : List Consumer
  deriving Repr

def select (known : List Equation) : List Nat → Option (List Equation)
  | [] => some []
  | i :: ids => do
      let e ← known[i]?
      let es ← select known ids
      some (e :: es)

/-- The optional transitivity link must start at exactly the claimed endpoint. -/
def residual (known : List Equation) (claim : Equation) : Option Nat → Option Equation
  | none => some claim
  | some i => do
      let prior ← known[i]?
      if prior.1 = claim.1 then some (prior.2, claim.2) else none

def derive (sorts : Nat) (sig : Signature) (known : List Equation) (d : Derivation) : Bool :=
  match d.request.decode, select known d.premises, residual known d.claim d.via with
  | some c, some es, some q =>
      c.sorts == sorts && decide (c.signature = sig) && decide (c.equations = es) &&
      decide (c.queries[d.query]? = some q) && sameSort sig d.claim.1 d.claim.2 &&
      QKFGround.check c d.certificate
  | _, _, _ => false

def acceptEntry (sorts : Nat) (sig : Signature) (base known : List Equation) : Entry → Option Equation
  | .native i => do
      let e ← base[i]?
      if sameSort sig e.1 e.2 then some e else none
  | .derived d => if derive sorts sig known d then some d.claim else none

def replay (sorts : Nat) (sig : Signature) (base : List Equation) :
    List Entry → List Equation → Option (List Equation)
  | [], known => some known
  | e :: es, known => do
      let q ← acceptEntry sorts sig base known e
      replay sorts sig base es (known ++ [q])

def consumer (sig : Signature) (known : List Equation) (g : Consumer) : Bool :=
  decide (known[g.index]? = some g.claim) && sameSort sig g.claim.1 g.claim.2

def check (p : Packet) : Bool :=
  p.sorts > 0 &&
  p.signature.all (fun s => s.result < p.sorts && s.args.all (· < p.sorts)) &&
  match replay p.sorts p.signature p.assumptions p.entries [] with
  | none => false
  | some known => p.consumers.all (consumer p.signature known)

end QKFComposition
