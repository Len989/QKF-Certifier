import Std

namespace QKFGround

/-- Names are assigned finite indices by the external JSON adapter. -/
structure Symbol where
  args : List Nat
  result : Nat
  deriving DecidableEq, Repr

abbrev Signature := List Symbol

inductive Term where
  | app : Nat → List Term → Term
  deriving Repr

mutual
  def termDecEq : (a b : Term) → Decidable (a = b)
    | .app f as, .app g bs =>
      if hf : f = g then
        match termsDecEq as bs with
        | isTrue h => isTrue (by cases hf; cases h; rfl)
        | isFalse h => isFalse (by intro he; cases he; exact h rfl)
      else isFalse (by intro he; cases he; exact hf rfl)
  termination_by structural a _ => a
  def termsDecEq : (as bs : List Term) → Decidable (as = bs)
    | [], [] => isTrue rfl
    | [], _ :: _ => isFalse (by intro h; cases h)
    | _ :: _, [] => isFalse (by intro h; cases h)
    | a :: as, b :: bs =>
      match termDecEq a b with
      | isFalse h => isFalse (by intro he; cases he; exact h rfl)
      | isTrue h =>
        match termsDecEq as bs with
        | isTrue ht => isTrue (by cases h; cases ht; rfl)
        | isFalse ht => isFalse (by intro he; cases he; exact ht rfl)
  termination_by structural as _ => as
end

instance : DecidableEq Term := termDecEq
instance : BEq Term := ⟨fun a b => decide (a = b)⟩
instance : LawfulBEq Term where
  rfl := by intro a; simp [BEq.beq]
  eq_of_beq := by intro a b h; exact of_decide_eq_true h

mutual
  def Term.sort (sig : Signature) : Term → Option Nat
    | .app op args => do
        let spec ← sig[op]?
        let sorts ← sortArgs sig args
        if sorts = spec.args then some spec.result else none
  termination_by structural t => t
  def sortArgs (sig : Signature) : List Term → Option (List Nat)
    | [] => some []
    | t :: ts => do
        let s ← t.sort sig
        let ss ← sortArgs sig ts
        some (s :: ss)
  termination_by structural ts => ts
end

theorem sortArgs_eq_mapM (sig : Signature) (ts : List Term) :
    sortArgs sig ts = ts.mapM (Term.sort sig) := by
  induction ts with
  | nil => rfl
  | cons t ts ih => simp [sortArgs, ih]

mutual
  def Term.depth : Term → Nat
    | .app _ [] => 0
    | .app _ (t :: ts) => 1 + max t.depth (depthArgs ts)
  termination_by structural t => t
  def depthArgs : List Term → Nat
    | [] => 0
    | t :: ts => max t.depth (depthArgs ts)
  termination_by structural ts => ts
end

/- A total algebra, also used below for the option-lifted typed semantics. -/
mutual
  def Term.eval {V : Type u} (op : Nat → List V → V) : Term → V
    | .app f args => op f (evalArgs op args)
  termination_by structural t => t
  def evalArgs {V : Type u} (op : Nat → List V → V) : List Term → List V
    | [] => []
    | t :: ts => t.eval op :: evalArgs op ts
  termination_by structural ts => ts
end

theorem evalArgs_eq_map {V : Type u} (op : Nat → List V → V) (ts : List Term) :
    evalArgs op ts = ts.map (Term.eval op) := by
  induction ts with
  | nil => rfl
  | cons t ts ih => simp [evalArgs, ih]

structure Node where
  op : Nat
  args : List Nat
  deriving DecidableEq, Repr

/-- The previous prior is the only source of child references. -/
def decodeNodes (sig : Signature) : List Node → List Term → Option (List Term)
  | [], prior => some prior
  | node :: rest, prior => do
      let args ← node.args.mapM (fun i => prior[i]?)
      let term := Term.app node.op args
      let _ ← term.sort sig
      decodeNodes sig rest (prior ++ [term])

abbrev Pair := Nat × Nat
abbrev Equation := Term × Term

def resolve (terms : List Term) (p : Pair) : Option Equation := do
  let a ← terms[p.1]?
  let b ← terms[p.2]?
  some (a, b)

def sameSort (sig : Signature) (a b : Term) : Bool :=
  match a.sort sig, b.sort sig with
  | some s, some t => s == t
  | _, _ => false

structure Context where
  sorts : Nat
  signature : Signature
  terms : List Term
  equations : List Equation
  queries : List Equation
  deriving Repr

def Context.valid (c : Context) : Bool :=
  c.sorts > 0 &&
  c.signature.all (fun s => s.result < c.sorts && s.args.all (· < c.sorts)) &&
  c.terms.all (fun t => (t.sort c.signature).isSome) &&
  (c.equations ++ c.queries).all (fun (a, b) =>
    c.terms.contains a && c.terms.contains b && sameSort c.signature a b)

structure Request where
  sorts : Nat
  signature : Signature
  nodes : List Node
  equations : List Pair
  queries : List Pair
  deriving Repr

def Request.decode (r : Request) : Option Context := do
  let terms ← decodeNodes r.signature r.nodes []
  let equations ← r.equations.mapM (resolve terms)
  let queries ← r.queries.mapM (resolve terms)
  let c := Context.mk r.sorts r.signature terms equations queries
  if c.valid then some c else none

def Models {V : Type u} (op : Nat → List V → V) (eqs : List Equation) : Prop :=
  ∀ e ∈ eqs, e.1.eval op = e.2.eval op

/-- A genuinely many-sorted interpretation: no common carrier or default element
is assumed. Operations consume exactly the declared sequence of sorts. -/
structure Interpretation (sig : Signature) where
  Carrier : Nat → Type u
  apply : (id : Nat) → (spec : Symbol) → sig[id]? = some spec →
    (values : List (Sigma Carrier)) → values.map Sigma.fst = spec.args → Carrier spec.result

/-- Lifting to an option of tagged values gives total operations even for empty
sorts. Ill-typed applications return none, rather than inventing a default. -/
def Interpretation.algebra {sig : Signature} (M : Interpretation sig)
    (id : Nat) (args : List (Option (Sigma M.Carrier))) : Option (Sigma M.Carrier) := do
  let spec ← sig[id]?
  let values ← args.mapM (fun x => x)
  if h : values.map Sigma.fst = spec.args then
    if hs : sig[id]? = some spec then
      some ⟨spec.result, M.apply id spec hs values h⟩
    else none
  else none

end QKFGround
