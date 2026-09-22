import Composition.Checker

namespace QKFComposition
open QKFGround

theorem select_sound {V : Type u} (op : Nat → List V → V) (known : List Equation)
    (sound : Models op known) (ids : List Nat) (selected : List Equation)
    (accepted : select known ids = some selected) : Models op selected := by
  induction ids generalizing selected with
  | nil =>
    have h : selected = [] := (Option.some.inj accepted).symm
    subst selected
    simp [Models]
  | cons i ids ih =>
    simp only [select, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
    obtain ⟨e, he, es, hes, hout⟩ := accepted
    cases Option.some.inj hout
    intro q hq
    rcases List.mem_cons.mp hq with hq | hq
    · subst q
      exact sound e (List.mem_of_getElem? he)
    · exact ih es hes q hq

/-- Importing a prior result proves the full claim by transitivity. The residual
is not itself the consumer claim, and the imported result is not a new axiom. -/
theorem residual_sound {V : Type u} (op : Nat → List V → V) (known : List Equation)
    (sound : Models op known) (claim q : Equation) (via : Option Nat)
    (accepted : residual known claim via = some q)
    (proved : q.1.eval op = q.2.eval op) : claim.1.eval op = claim.2.eval op := by
  cases via with
  | none => cases Option.some.inj accepted; exact proved
  | some i =>
    simp only [residual, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
    obtain ⟨prior, hp, h⟩ := accepted
    split at h
    · rename_i he
      cases Option.some.inj h
      have hs := sound prior (List.mem_of_getElem? hp)
      exact (he ▸ hs).trans proved
    · contradiction

theorem derive_sound {V : Type u} (op : Nat → List V → V)
    (sorts : Nat) (sig : Signature) (known : List Equation) (d : Derivation)
    (sound : Models op known) (accepted : derive sorts sig known d = true) :
    d.claim.1.eval op = d.claim.2.eval op := by
  unfold derive at accepted
  split at accepted
  · rename_i c es q hc hs hr
    simp only [Bool.and_eq_true, decide_eq_true_eq] at accepted
    have eqs := accepted.1.1.1.2
    have query := accepted.1.1.2
    have hm : Models op c.equations := eqs ▸ select_sound op known sound d.premises es hs
    have hq : q ∈ c.queries := List.mem_of_getElem? query
    exact residual_sound op known sound d.claim q d.via hr
      (QKFGround.check_sound op c d.certificate accepted.2 hm q hq)
  · contradiction

theorem entry_sound {V : Type u} (op : Nat → List V → V)
    (sorts : Nat) (sig : Signature) (base known : List Equation)
    (models : Models op base) (sound : Models op known) (e : Entry) (q : Equation)
    (accepted : acceptEntry sorts sig base known e = some q) : q.1.eval op = q.2.eval op := by
  cases e with
  | native i =>
    simp only [acceptEntry, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
    obtain ⟨a, ha, h⟩ := accepted
    split at h
    · cases Option.some.inj h
      exact models q (List.mem_of_getElem? ha)
    · contradiction
  | derived d =>
    simp only [acceptEntry] at accepted
    split at accepted
    · rename_i h
      cases Option.some.inj accepted
      exact derive_sound op sorts sig known d sound h
    · contradiction

/-- Every entry admitted along E → E+ follows from the original native
assumptions. This also covers unused lemmas, not just consumer-reachable ones. -/
theorem replay_sound {V : Type u} (op : Nat → List V → V)
    (sorts : Nat) (sig : Signature) (base : List Equation) (models : Models op base)
    (es : List Entry) (known result : List Equation) (sound : Models op known)
    (accepted : replay sorts sig base es known = some result) : Models op result := by
  induction es generalizing known with
  | nil => exact (Option.some.inj accepted) ▸ sound
  | cons e es ih =>
    simp only [replay, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
    obtain ⟨q, hq, ht⟩ := accepted
    apply ih (known ++ [q]) _ ht
    intro r hr
    rcases List.mem_append.mp hr with hr | hr
    · exact sound r hr
    · have he : r = q := by simpa using hr
      subst r
      exact entry_sound op sorts sig base known models sound e q hq

theorem consumer_sound {V : Type u} (op : Nat → List V → V)
    (sig : Signature) (known : List Equation) (sound : Models op known)
    (g : Consumer) (accepted : consumer sig known g = true) :
    g.claim.1.eval op = g.claim.2.eval op := by
  simp only [consumer, Bool.and_eq_true, decide_eq_true_eq] at accepted
  exact sound g.claim (List.mem_of_getElem? accepted.1)

/-- Adding the checked prefix to E does not remove any model of E. -/
theorem conservative_extension {V : Type u} (op : Nat → List V → V)
    (p : Packet) (known : List Equation)
    (accepted : replay p.sorts p.signature p.assumptions p.entries [] = some known) :
    Models op (p.assumptions ++ known) ↔ Models op p.assumptions := by
  constructor
  · intro h e he
    exact h e (List.mem_append_left _ he)
  · intro h e he
    rcases List.mem_append.mp he with he | he
    · exact h e he
    · exact replay_sound op p.sorts p.signature p.assumptions h p.entries [] known
        (by simp [Models]) accepted e he

theorem check_replay (p : Packet) (accepted : check p = true) :
    ∃ known, replay p.sorts p.signature p.assumptions p.entries [] = some known ∧
      p.consumers.all (consumer p.signature known) = true := by
  simp only [check, Bool.and_eq_true] at accepted
  have h := accepted.2
  split at h
  · contradiction
  · rename_i known hr
    exact ⟨known, hr, h⟩

theorem all_admitted_sound {V : Type u} (op : Nat → List V → V)
    (p : Packet) (accepted : check p = true) (models : Models op p.assumptions) :
    ∃ known, replay p.sorts p.signature p.assumptions p.entries [] = some known ∧
      Models op known := by
  obtain ⟨known, hr, _⟩ := check_replay p accepted
  exact ⟨known, hr, replay_sound op p.sorts p.signature p.assumptions models
    p.entries [] known (by simp [Models]) hr⟩

theorem check_sound {V : Type u} (op : Nat → List V → V)
    (p : Packet) (accepted : check p = true) (models : Models op p.assumptions)
    (g : Consumer) (member : g ∈ p.consumers) : g.claim.1.eval op = g.claim.2.eval op := by
  obtain ⟨known, hr, hg⟩ := check_replay p accepted
  have sound := replay_sound op p.sorts p.signature p.assumptions models
    p.entries [] known (by simp [Models]) hr
  exact consumer_sound op p.signature known sound g (List.all_eq_true.mp hg g member)

theorem accepted_consumer_typed (p : Packet) (accepted : check p = true)
    (g : Consumer) (member : g ∈ p.consumers) :
    ∃ s, g.claim.1.sort p.signature = some s ∧ g.claim.2.sort p.signature = some s := by
  obtain ⟨known, _, hg⟩ := check_replay p accepted
  have h := List.all_eq_true.mp hg g member
  simp only [consumer, Bool.and_eq_true] at h
  have hs := h.2
  unfold sameSort at hs
  split at hs
  · rename_i s t ha hb
    have eq : s = t := of_decide_eq_true hs
    exact ⟨s, ha, eq ▸ hb⟩
  · contradiction

/-- Every accepted consumer has the same actual value at both endpoints in
every typed model of the original assumptions. No equality of failures. -/
theorem accepted_consumer_values (p : Packet) (accepted : check p = true)
    (M : Interpretation p.signature) (models : Models M.algebra p.assumptions)
    (g : Consumer) (member : g ∈ p.consumers) :
    ∃ s, ∃ v : M.Carrier s,
      g.claim.1.eval M.algebra = some ⟨s, v⟩ ∧
      g.claim.2.eval M.algebra = some ⟨s, v⟩ := by
  obtain ⟨s, ha, _⟩ := accepted_consumer_typed p accepted g member
  obtain ⟨v, hv⟩ := eval_typed M g.claim.1 s ha
  have eq := check_sound M.algebra p accepted models g member
  exact ⟨s, v, hv, eq ▸ hv⟩

end QKFComposition
