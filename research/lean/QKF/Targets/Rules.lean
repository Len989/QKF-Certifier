import QKF.Targets.Numeric

namespace QKF.Targets

inductive Variable where
  | must | may | seed | output | alternative | bound
  deriving DecidableEq, Repr

abbrev Env := Variable → Bool

inductive WordExpr where
  | var (v : Variable)
  | zero | ones
  | bitNot (x : WordExpr)
  | bitAnd (x y : WordExpr)
  | bitOr (x y : WordExpr)
  | bitXor (x y : WordExpr)
  deriving DecidableEq, Repr

def bit : WordExpr → Env → Bool
  | .var v, e => e v
  | .zero, _ => false
  | .ones, _ => true
  | .bitNot x, e => !(bit x e)
  | .bitAnd x y, e => bit x e && bit y e
  | .bitOr x y, e => bit x e || bit y e
  | .bitXor x y, e => bit x e != bit y e

/- Numerical semantics of a coordinatewise expression, not a state-table lookup. -/
def number (x : WordExpr) (history : List Env) : Nat :=
  value (history.map (bit x))

theorem number_bound (x : WordExpr) (history : List Env) :
    number x history < 2 ^ history.length := by
  simpa [number] using value_bound (history.map (bit x))

theorem number_snoc (x : WordExpr) (history : List Env) (e : Env) :
    number x (history ++ [e]) = number x history + digit (bit x e) * 2 ^ history.length := by
  simpa [number] using value_snoc (history.map (bit x)) (bit x e)

inductive Kind where
  | eq | subset | disjoint | order
  deriving DecidableEq, Repr

structure Atom where
  kind : Kind
  left : WordExpr
  right : WordExpr
  deriving DecidableEq, Repr

inductive Answer where
  | boolean (b : Bool)
  | ordering (r : Order)
  deriving DecidableEq, Repr, Inhabited

def Answer.asBool : Answer → Bool
  | .boolean b => b
  | .ordering _ => false

def Answer.asOrder : Answer → Order
  | .ordering r => r
  | .boolean _ => .eq

def atomStart (a : Atom) : Answer :=
  match a.kind with
  | .order => .ordering .eq
  | _ => .boolean true

def atomStep (a : Atom) (old : Answer) (e : Env) : Answer :=
  let l := bit a.left e
  let r := bit a.right e
  match a.kind with
  | .order => .ordering (higher l r old.asOrder)
  | .eq => .boolean (old.asBool && (l == r))
  | .subset => .boolean (old.asBool && (!l || r))
  | .disjoint => .boolean (old.asBool && !(l && r))

/- Support inclusion/disjointness mean exactly their tests at EVERY bit. -/
def support (x y : WordExpr) (h : List Env) : Bool :=
  h.all (fun e => !(bit x e) || bit y e)

def apart (x y : WordExpr) (h : List Env) : Bool :=
  h.all (fun e => !(bit x e && bit y e))

def atomMeaning (a : Atom) (h : List Env) : Answer :=
  match a.kind with
  | .order => .ordering (compare (number a.left h) (number a.right h))
  | .eq => .boolean (decide (number a.left h = number a.right h))
  | .subset => .boolean (support a.left a.right h)
  | .disjoint => .boolean (apart a.left a.right h)

theorem atom_empty (a : Atom) : atomMeaning a [] = atomStart a := by
  cases a with
  | mk k l r => cases k <;> rfl

theorem atom_snoc (a : Atom) (h : List Env) (e : Env) :
    atomMeaning a (h ++ [e]) = atomStep a (atomMeaning a h) e := by
  have hl := number_bound a.left h
  have hr := number_bound a.right h
  cases a with
  | mk k l r =>
    cases k
    · simp only [atomMeaning, atomStep, Answer.asBool, number_snoc]
      rw [extend_eq hl hr]
      simp
    · simp [atomMeaning, atomStep, Answer.asBool, support, List.all_append]
    · simp [atomMeaning, atomStep, Answer.asBool, apart, List.all_append]
    · simp only [atomMeaning, atomStep, Answer.asOrder, number_snoc]
      rw [compare_higher hl hr]

inductive Formula (n : Nat) where
  | literal (b : Bool)
  | query (i : Fin n)
  | ult (i : Fin n)
  | ule (i : Fin n)
  | neg (p : Formula n)
  | conj (p q : Formula n)
  | disj (p q : Formula n)
  | implies (p q : Formula n)
  deriving DecidableEq, Repr

def evaluate {n : Nat} : Formula n → (Fin n → Answer) → Bool
  | .literal b, _ => b
  | .query i, o => (o i).asBool
  | .ult i, o => (o i).asOrder == .lt
  | .ule i, o => (o i).asOrder != .gt
  | .neg p, o => !(evaluate p o)
  | .conj p q, o => evaluate p o && evaluate q o
  | .disj p q, o => evaluate p o || evaluate q o
  | .implies p q, o => !(evaluate p o) || evaluate q o

structure Program (n : Nat) where
  atoms : Fin n → Atom
  precondition : Formula n
  obligation : Formula n

def wellTyped {n : Nat} (p : Program n) : Formula n → Bool
  | .literal _ => true
  | .query i => (p.atoms i).kind != .order
  | .ult i | .ule i => (p.atoms i).kind == .order
  | .neg q => wellTyped p q
  | .conj q r | .disj q r | .implies q r => wellTyped p q && wellTyped p r

def meaning {n : Nat} (p : Program n) (h : List Env) : Fin n → Answer :=
  fun i => atomMeaning (p.atoms i) h

def advance {n : Nat} (p : Program n) (o : Fin n → Answer) (e : Env) : Fin n → Answer :=
  fun i => atomStep (p.atoms i) (o i) e

theorem advance_meaning {n : Nat} (p : Program n) (h : List Env) (e : Env) :
    advance p (meaning p h) e = meaning p (h ++ [e]) := by
  funext i
  exact (atom_snoc (p.atoms i) h e).symm

def semanticGoal {n : Nat} (p : Program n) (h : List Env) : Bool :=
  !(evaluate p.precondition (meaning p h)) || evaluate p.obligation (meaning p h)

end QKF.Targets
