import Ground.Soundness

namespace QKFGround

theorem sequence_some {α : Type u} (xs : List α) :
    (xs.map some).mapM (fun x => x) = some xs := by
  induction xs with
  | nil => rfl
  | cons x xs ih =>
    simp only [List.map_cons, List.mapM_cons, Option.bind_eq_bind, Option.bind_some, ih]
    rfl

/-- A well-typed term really evaluates to a value of its declared carrier.
Thus the typed soundness theorem is not an equality of two decoding failures. -/
theorem eval_typed {sig : Signature} (M : Interpretation sig) (t : Term) :
    ∀ s, t.sort sig = some s →
      ∃ v : M.Carrier s, t.eval M.algebra = some ⟨s, v⟩ := by
  induction t using Term.rec (motive_2 := fun ts =>
    ∀ sorts, ts.mapM (Term.sort sig) = some sorts →
      ∃ values : List (Sigma M.Carrier),
        ts.map (Term.eval M.algebra) = values.map some ∧ values.map Sigma.fst = sorts) with
  | app op args ih =>
    intro s typed
    simp only [Term.sort, sortArgs_eq_mapM, Option.bind_eq_bind, Option.bind_eq_some_iff] at typed
    obtain ⟨spec, hs, sorts, hsorts, hresult⟩ := typed
    split at hresult
    · rename_i he
      have hr : spec.result = s := Option.some.inj hresult
      subst s
      obtain ⟨values, hv, htypes⟩ := ih sorts hsorts
      have correct : values.map Sigma.fst = spec.args := htypes.trans he
      refine ⟨M.apply op spec hs values correct, ?_⟩
      simp only [Term.eval, evalArgs_eq_map, hv, Interpretation.algebra, hs, Option.bind_eq_bind,
        Option.bind_some, sequence_some]
      simp only [correct, dite_true]
    · contradiction
  | nil =>
    rename_i sorts h
    have hs : sorts = [] := by simpa using h.symm
    subst sorts
    exact ⟨[], rfl, rfl⟩
  | cons t ts ht hs =>
    rename_i sorts typed
    simp only [List.mapM_cons, Option.bind_eq_bind, Option.bind_eq_some_iff] at typed
    obtain ⟨s, ht', ss, hs', hresult⟩ := typed
    have hr : s :: ss = sorts := Option.some.inj hresult
    subst sorts
    obtain ⟨v, hv⟩ := ht s ht'
    obtain ⟨values, hv', hsorts⟩ := hs ss hs'
    exact ⟨⟨s, v⟩ :: values, by simp [hv, hv'], by simp [hsorts]⟩

/-- The public typed statement includes actual values, not just option equality. -/
theorem typed_goal_sound (c : Context) (cert : Certificate)
    (accepted : check c cert = true) (M : Interpretation c.signature)
    (models : Models M.algebra c.equations) (a b : Term)
    (member : (a, b) ∈ c.queries) (s : Nat) (typed : a.sort c.signature = some s) :
    ∃ v : M.Carrier s, a.eval M.algebra = some ⟨s, v⟩ ∧
      b.eval M.algebra = some ⟨s, v⟩ := by
  obtain ⟨v, hv⟩ := eval_typed M a s typed
  have equal := typed_check_sound c cert accepted M models (a, b) member
  exact ⟨v, hv, equal ▸ hv⟩

theorem accepted_query_typed (c : Context) (cert : Certificate)
    (accepted : check c cert = true) (a b : Term) (member : (a, b) ∈ c.queries) :
    ∃ s, a.sort c.signature = some s ∧ b.sort c.signature = some s := by
  simp only [check, Bool.and_eq_true] at accepted
  have valid := accepted.1.1
  simp only [Context.valid, Bool.and_eq_true] at valid
  have h := List.all_eq_true.mp valid.2 (a, b) (List.mem_append_right _ member)
  simp only [Bool.and_eq_true] at h
  have hs := h.2
  unfold sameSort at hs
  split at hs
  · rename_i s t ha hb
    have eq : s = t := of_decide_eq_true hs
    exact ⟨s, ha, eq ▸ hb⟩
  · contradiction

/-- Acceptance alone provides well-typed endpoints; every model of E gives
both endpoints the very same value in their common carrier. -/
theorem accepted_goal_values (c : Context) (cert : Certificate)
    (accepted : check c cert = true) (M : Interpretation c.signature)
    (models : Models M.algebra c.equations) (a b : Term) (member : (a, b) ∈ c.queries) :
    ∃ s, ∃ v : M.Carrier s,
      a.eval M.algebra = some ⟨s, v⟩ ∧ b.eval M.algebra = some ⟨s, v⟩ := by
  obtain ⟨s, ha, _⟩ := accepted_query_typed c cert accepted a b member
  obtain ⟨v, hv⟩ := typed_goal_sound c cert accepted M models a b member s ha
  exact ⟨s, v, hv⟩

end QKFGround
