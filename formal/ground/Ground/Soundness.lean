import Ground.Checker

namespace QKFGround

def Sound {V : Type u} (op : Nat → List V → V) (facts : List Fact) : Prop :=
  ∀ f ∈ facts, f.left.eval op = f.right.eval op

theorem walk_sound {V : Type u} (op : Nat → List V → V) (facts : List Fact)
    (known : Sound op facts) (ids : List Nat) (a b : Term) (cost : Nat)
    (accepted : walk facts a ids = some (b, cost)) : a.eval op = b.eval op := by
  induction ids generalizing a b cost with
  | nil => simpa [walk] using congrArg (fun x => x.map (fun z => z.1.eval op)) accepted
  | cons i ids ih =>
    simp only [walk, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
    obtain ⟨edge, he, next, hn, result, hr, hout⟩ := accepted
    have edgeSound := known edge (List.mem_of_getElem? he)
    have stepEq : a.eval op = next.eval op := by
      unfold step at hn
      split at hn
      · rename_i h
        cases Option.some.inj hn
        simpa [h] using edgeSound
      · split at hn
        · rename_i h
          cases Option.some.inj hn
          simpa [h] using edgeSound.symm
        · contradiction
    have tail := ih next result.1 result.2 hr
    have endEq : result.1 = b := congrArg (fun x => x.1) (Option.some.inj hout)
    exact stepEq.trans (endEq ▸ tail)

theorem path_sound {V : Type u} (op : Nat → List V → V) (facts : List Fact)
    (known : Sound op facts) (a b : Term) (ids : List Nat) (cost : Nat)
    (accepted : path facts a b ids = some cost) : a.eval op = b.eval op := by
  simp only [path, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
  obtain ⟨result, hr, h⟩ := accepted
  split at h
  · rename_i hb
    exact hb ▸ walk_sound op facts known ids a result.1 result.2 hr
  · contradiction

theorem arguments_sound {V : Type u} (op : Nat → List V → V) (facts : List Fact)
    (known : Sound op facts) (as bs : List Term) (ps : List (List Nat)) (cost : Nat)
    (accepted : arguments facts as bs ps = some cost) :
    as.map (Term.eval op) = bs.map (Term.eval op) := by
  induction as generalizing bs ps cost with
  | nil => cases bs <;> cases ps <;> simp_all [arguments]
  | cons a as ih =>
    cases bs with
    | nil => simp [arguments] at accepted
    | cons b bs =>
      cases ps with
      | nil => simp [arguments] at accepted
      | cons ids ps =>
        simp only [arguments, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
        obtain ⟨head, hh, tail, ht, _⟩ := accepted
        simp only [List.map_cons, path_sound op facts known a b ids head hh,
          ih bs ps tail ht]

theorem event_sound {V : Type u} (op : Nat → List V → V) (c : Context)
    (models : Models op c.equations) (facts : List Fact) (known : Sound op facts)
    (horizon : Nat) (e : Event) (f : Fact) (accepted : event c horizon facts e = some f) :
    f.left.eval op = f.right.eval op := by
  simp only [event, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
  obtain ⟨a, _, b, _, accepted⟩ := accepted
  split at accepted
  · contradiction
  · simp only [Option.bind_eq_some_iff] at accepted
    obtain ⟨cost, hc, hout⟩ := accepted
    have endpoints : f.left = a ∧ f.right = b := by
      split at hout
      · cases Option.some.inj hout; exact ⟨rfl, rfl⟩
      · contradiction
    rw [endpoints.1, endpoints.2]
    cases heq : e.rule with
    | «axiom» i =>
      simp only [heq, eventCost, Option.bind_eq_bind, Option.bind_eq_some_iff] at hc
      obtain ⟨eq, he, h⟩ := hc
      have hs := models eq (List.mem_of_getElem? he)
      split at h
      · rename_i hpair
        rcases hpair with ⟨ha, hb⟩ | ⟨ha, hb⟩
        · simpa [ha, hb] using hs
        · simpa [ha, hb] using hs.symm
      · contradiction
    | congruence ps =>
      simp only [heq, eventCost] at hc
      cases a with | app x as =>
       cases b with | app y bs =>
        dsimp only at hc
        split at hc
        · rename_i hh
          simp only [Option.bind_eq_bind, Option.bind_eq_some_iff] at hc
          obtain ⟨cost, hp, _⟩ := hc
          simp only [Term.eval, evalArgs_eq_map, hh, arguments_sound op facts known as bs ps cost hp]
        · contradiction

theorem events_sound {V : Type u} (op : Nat → List V → V) (c : Context)
    (models : Models op c.equations) (horizon : Nat) (es : List Event)
    (facts result : List Fact) (known : Sound op facts)
    (accepted : events c horizon es facts = some result) : Sound op result := by
  induction es generalizing facts with
  | nil =>
    have h : facts = result := Option.some.inj accepted
    exact h ▸ known
  | cons e es ih =>
    simp only [events, Option.bind_eq_bind, Option.bind_eq_some_iff] at accepted
    obtain ⟨f, hf, ht⟩ := accepted
    apply ih (facts ++ [f]) _ ht
    intro g hg
    rcases List.mem_append.mp hg with hg | hg
    · exact known g hg
    · have he : g = f := by simpa using hg
      subst g
      exact event_sound op c models facts known horizon e f hf

theorem goals_sound {V : Type u} (op : Nat → List V → V) (horizon : Nat)
    (facts : List Fact) (known : Sound op facts) (qs : List Equation) (gs : List Goal)
    (accepted : goals horizon facts qs gs = true) : Models op qs := by
  induction qs generalizing gs with
  | nil => simp [Models]
  | cons q qs ih =>
    cases gs with
    | nil => simp [goals] at accepted
    | cons g gs =>
      unfold goals at accepted
      split at accepted
      · contradiction
      · rename_i cost hc
        simp only [Bool.and_eq_true] at accepted
        intro r hr
        rcases List.mem_cons.mp hr with hr | hr
        · subst r
          exact path_sound op facts known q.1 q.2 g.path cost hc
        · exact ih gs accepted.2 r hr

/-- Every accepted positive goal follows in every total algebra satisfying E.
This is stronger than the typed instance below, and does not assume that E has
a model, that the search is complete, or that the horizon is minimal. -/
theorem check_sound {V : Type u} (op : Nat → List V → V) (c : Context)
    (cert : Certificate) (accepted : check c cert = true)
    (models : Models op c.equations) : Models op c.queries := by
  simp only [check, Bool.and_eq_true] at accepted
  have h := accepted.2
  split at h
  · contradiction
  · rename_i facts he
    have initial : Sound op [] := by simp [Sound]
    exact goals_sound op cert.horizon facts
      (events_sound op c models cert.horizon cert.events [] facts initial he)
      c.queries cert.goals h

theorem typed_check_sound (c : Context) (cert : Certificate)
    (accepted : check c cert = true) (M : Interpretation c.signature)
    (models : Models M.algebra c.equations) : Models M.algebra c.queries :=
  check_sound M.algebra c cert accepted models

/-- Raw DAG syntax is decoded by Lean before the proof checker is called.
The external JSON adapter is not assumed to establish logical soundness. -/
theorem checkRaw_sound (r : Request) (cert : Certificate)
    (accepted : checkRaw r cert = true) :
    ∃ c, r.decode = some c ∧ check c cert = true ∧
      ∀ (M : Interpretation c.signature), Models M.algebra c.equations → Models M.algebra c.queries := by
  unfold checkRaw at accepted
  split at accepted
  · contradiction
  · rename_i c hc
    exact ⟨c, hc, accepted, fun M hm => typed_check_sound c cert accepted M hm⟩

end QKFGround
