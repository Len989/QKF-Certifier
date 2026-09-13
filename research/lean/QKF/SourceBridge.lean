import QKF.WordSemantics

namespace QKF

/- An explicit iteration of sourceCell. Only the nonsign repair loop is
modeled here. The external optionalBits == 0 branch is not hidden in it. -/
structure SourceWordState where
  width : Nat
  g : Nat
  x : Nat
  t : Nat
  phase : Phase
  trace : List (Column × Bool)

def sourceWordStart : SourceWordState := ⟨0, 0, 0, 0, .before, []⟩

def observeSource (s : SourceWordState) : WordState :=
  ⟨s.width, s.g, s.x, s.t, phaseObservation s.phase, s.trace⟩

def sourceWordStep (s : SourceWordState) (c : Column) : SourceWordState :=
  let action := sourceCell s.phase c
  ⟨s.width + 1, s.g + digit (inputBit c) * 2 ^ s.width,
    s.x + digit (candidateBit c) * 2 ^ s.width,
    s.t + digit action.1 * 2 ^ s.width, action.2,
    s.trace ++ [(c, action.1)]⟩

theorem source_step_factor (s : SourceWordState) (c : Column) :
    observeSource (sourceWordStep s c) = wordStep (observeSource s) c := by
  have h₁ : (sourceCell s.phase c).1 = (nativeStep c (phaseObservation s.phase)).1 :=
    congrArg Prod.fst (source_phase_factor s.phase c)
  have h₂ : phaseObservation (sourceCell s.phase c).2 =
      (nativeStep c (phaseObservation s.phase)).2 :=
    congrArg Prod.snd (source_phase_factor s.phase c)
  simp only [observeSource, sourceWordStep, wordStep, glued_cell_correct]
  rw [h₁, h₂]

theorem source_word_factor (columns : List Column) :
    observeSource (run sourceWordStep sourceWordStart columns) =
      run wordStep wordStart columns := by
  exact run_simulation sourceWordStep wordStep observeSource source_step_factor
    columns sourceWordStart

end QKF
