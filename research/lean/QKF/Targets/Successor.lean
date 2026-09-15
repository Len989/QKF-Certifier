import QKF.Targets.Kernel

namespace QKF.Targets

/- Independent goal, not read from the certificate. The exported program must
be equal to this one before the named successor theorem can be applied. -/
def successorProgram : Program 7 where
  atoms := fun i => match i.val with
    | 0 => ⟨.subset, .var .must, .var .output⟩
    | 1 => ⟨.subset, .var .output, .var .may⟩
    | 2 => ⟨.eq, .var .seed, .var .may⟩
    | 3 => ⟨.order, .var .seed, .var .output⟩
    | 4 => ⟨.order, .var .seed, .var .alternative⟩
    | 5 => ⟨.order, .var .output, .var .alternative⟩
    | _ => ⟨.eq, .var .output, .var .must⟩
  precondition := .literal true
  obligation := .conj (.query 0) (.conj (.query 1)
    (.conj (.implies (.neg (.query 2)) (.ult 3))
    (.conj (.implies (.ult 4) (.ule 5))
    (.conj (.implies (.query 2) (.query 6)) (.literal true)))))

def CyclicPost (h : List Env) : Prop :=
  support (.var .must) (.var .output) h = true ∧
  support (.var .output) (.var .may) h = true ∧
  (number (.var .seed) h ≠ number (.var .may) h →
    number (.var .seed) h < number (.var .output) h) ∧
  (number (.var .seed) h < number (.var .alternative) h →
    number (.var .output) h ≤ number (.var .alternative) h) ∧
  (number (.var .seed) h = number (.var .may) h →
    number (.var .output) h = number (.var .must) h)

theorem successor_semantics (h : List Env) :
    semanticGoal successorProgram h = true ↔ CyclicPost h := by
  simp [semanticGoal, successorProgram, evaluate, meaning, atomMeaning,
    Answer.asBool, Answer.asOrder, CyclicPost, compare_lt, compare_le]

theorem successor_from_certificate {k size : Nat} (m : Machine k)
    (c : Certificate 7 k size) (accepted : checkCertificate m successorProgram c = true)
    (xs : List Column) (positive : xs ≠ []) : CyclicPost (execute m xs).history :=
  (successor_semantics _).mp (accepted_all_widths m successorProgram c accepted xs positive)

end QKF.Targets
