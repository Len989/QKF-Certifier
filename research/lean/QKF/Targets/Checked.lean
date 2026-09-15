import QKF.Targets.Data
import QKF.Targets.Words

set_option maxRecDepth 16384
set_option maxHeartbeats 4000000

namespace QKF.Targets

/- Each DATA program must match the protected external goal. -/
theorem original_goal : Data.originalProgram = successorProgram := rfl
theorem irrelevant_goal : Data.irrelevantProgram = successorProgram := rfl

theorem original_accepted :
    checkCertificate Data.originalMachine Data.originalProgram Data.originalCertificate = true := by decide

theorem irrelevant_accepted :
    checkCertificate Data.irrelevantMachine Data.irrelevantProgram Data.irrelevantCertificate = true := by decide

theorem original_cyclic_successor (is : List Input) (positive : is ≠ []) :
    CyclicSuccessor is (value (emitted Data.originalMachine Data.originalMachine.initial is)) := by
  apply cyclic_successor_all_widths Data.originalMachine Data.originalCertificate
  · rw [← original_goal]
    exact original_accepted
  · exact positive

theorem irrelevant_cyclic_successor (is : List Input) (positive : is ≠ []) :
    CyclicSuccessor is (value (emitted Data.irrelevantMachine Data.irrelevantMachine.initial is)) := by
  apply cyclic_successor_all_widths Data.irrelevantMachine Data.irrelevantCertificate
  · rw [← irrelevant_goal]
    exact irrelevant_accepted
  · exact positive

theorem original_singleton (is : List Input) (positive : is ≠ [])
    (same : value (is.map must) = value (is.map may)) :
    value (emitted Data.originalMachine Data.originalMachine.initial is) = value (is.map must) := by
  have bounds := (masked_extrema is).2.2 _ (original_cyclic_successor is positive).1
  omega

example : value (emitted Data.originalMachine 0 [2, 0, 1]) = 4 := by decide
example : value (emitted Data.originalMachine 0 [2, 0, 2]) = 0 := by decide
example : value (emitted Data.originalMachine 0 [3, 0, 3]) = 5 := by decide

end QKF.Targets

#print axioms QKF.Targets.atom_snoc
#print axioms QKF.Targets.accepted_all_widths
#print axioms QKF.Targets.cyclic_successor_all_widths
#print axioms QKF.Targets.original_accepted
#print axioms QKF.Targets.original_cyclic_successor
#print axioms QKF.Targets.irrelevant_cyclic_successor
#print axioms QKF.Targets.original_singleton
