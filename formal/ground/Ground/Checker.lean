import Ground.Syntax

namespace QKFGround

structure Fact where
  left : Term
  right : Term
  depth : Nat
  deriving DecidableEq, Repr

inductive Rule where
  | axiom (equation : Nat)
  | congruence (premises : List (List Nat))
  deriving DecidableEq, Repr

structure Event where
  left : Nat
  right : Nat
  depth : Nat
  rule : Rule
  deriving DecidableEq, Repr

structure Goal where
  path : List Nat
  depth : Nat
  deriving DecidableEq, Repr

structure Certificate where
  horizon : Nat
  events : List Event
  goals : List Goal
  deriving DecidableEq, Repr

def step (edge : Fact) (start : Term) : Option Term :=
  if start = edge.left then some edge.right
  else if start = edge.right then some edge.left else none

/-- Empty paths are reflexive; every edge can be traversed in either direction.
Only facts already admitted into this prefix are addressable. -/
def walk (facts : List Fact) : Term → List Nat → Option (Term × Nat)
  | start, [] => some (start, 0)
  | start, i :: rest => do
      let edge ← facts[i]?
      let next ← step edge start
      let (last, cost) ← walk facts next rest
      some (last, max edge.depth cost)

def path (facts : List Fact) (a b : Term) (ids : List Nat) : Option Nat := do
  let (last, cost) ← walk facts a ids
  if last = b then some (max (max a.depth b.depth) cost) else none

/-- Recursing over three lists enforces exact arity, including zero arity. -/
def arguments (facts : List Fact) : List Term → List Term → List (List Nat) → Option Nat
  | [], [], [] => some 0
  | a :: as, b :: bs, ids :: ps => do
      let cost ← path facts a b ids
      let tail ← arguments facts as bs ps
      some (max cost tail)
  | _, _, _ => none

def eventCost (c : Context) (facts : List Fact) (a b : Term) : Rule → Option Nat
  | .axiom i => do
      let (x, y) ← c.equations[i]?
      if (a = x ∧ b = y) ∨ (a = y ∧ b = x) then some (max a.depth b.depth) else none
  | .congruence premises =>
      match a, b with
      | .app f as, .app g bs =>
          if f = g then do
            let cost ← arguments facts as bs premises
            some (max (max a.depth b.depth) cost)
          else none

def event (c : Context) (horizon : Nat) (facts : List Fact) (e : Event) : Option Fact := do
  let a ← c.terms[e.left]?
  let b ← c.terms[e.right]?
  if !sameSort c.signature a b then none else do
    let cost ← eventCost c facts a b e.rule
    if e.depth = cost ∧ cost ≤ horizon then some ⟨a, b, cost⟩ else none

def events (c : Context) (horizon : Nat) : List Event → List Fact → Option (List Fact)
  | [], facts => some facts
  | e :: es, facts => do
      let proved ← event c horizon facts e
      events c horizon es (facts ++ [proved])

def goals (horizon : Nat) (facts : List Fact) : List Equation → List Goal → Bool
  | [], [] => true
  | (a, b) :: qs, g :: gs =>
      match path facts a b g.path with
      | none => false
      | some cost => g.depth == cost && cost ≤ horizon && goals horizon facts qs gs
  | _, _ => false

/-- Positive entailment only. No model or minimal-threshold claim is decoded. -/
def check (c : Context) (cert : Certificate) : Bool :=
  c.valid && cert.horizon ≤ (c.terms.map Term.depth).foldl max 0 &&
  match events c cert.horizon cert.events [] with
  | none => false
  | some facts => goals cert.horizon facts c.queries cert.goals

def checkRaw (request : Request) (cert : Certificate) : Bool :=
  match request.decode with
  | none => false
  | some c => check c cert

end QKFGround
