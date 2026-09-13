import QKF.Data
import QKF.Gluing

set_option maxRecDepth 4096
set_option maxHeartbeats 4000000

namespace QKF

theorem native_rows_cup : ∀ r : Fin 8, PreservesCup (nativeRow r) := by
  intro r ⟨a, b⟩ ⟨c, d⟩
  revert r a b c d
  decide

theorem native_rows_cap : ∀ r : Fin 8, PreservesCap (nativeRow r) := by
  intro r ⟨a, b⟩ ⟨c, d⟩
  revert r a b c d
  decide

theorem completed_rows_cup : ∀ r : Fin 8, PreservesCup (completedRow Data.rows r) := by
  intro r ⟨a, b⟩ ⟨c, d⟩
  revert r a b c d
  decide

theorem completed_rows_cap : ∀ r : Fin 8, PreservesCap (completedRow Data.rows r) := by
  intro r ⟨a, b⟩ ⟨c, d⟩
  revert r a b c d
  decide

theorem supplied_atoms_checked : ∀ (r : Fin 8) (b : Bool),
    completedRow Data.rows r (atom b) = nativeRow r (atom b) := by decide

/- General forced-row uniqueness connects the two supplied atoms to every
entry consumed by the word transition. -/
theorem forced_rows_correct (r : Fin 8) (p : Carrier) :
    completedRow Data.rows r p = nativeRow r p :=
  atoms_force_row _ _ (completed_rows_cup r) (completed_rows_cap r)
    (native_rows_cup r) (native_rows_cap r)
    (supplied_atoms_checked r false) (supplied_atoms_checked r true) p

theorem row_allows_correct (c : Column) (output next carry : Bool) :
    rowAllows Data.rows c output next carry =
      mem (nativeRow (labelIndex c output) (atom next)) carry := by
  have h := congrArg (fun p => mem p carry)
    (forced_rows_correct (labelIndex c output) (atom next))
  cases next <;> simpa [rowAllows, completedRow, encodeCarrier, atomCode, atom] using h

theorem glued_cell_correct : ∀ (c : Column) (carry : Bool),
    stepFromRows Data.rows c carry = nativeStep c carry := by
  intro c carry
  unfold stepFromRows
  rw [row_allows_correct, row_allows_correct, row_allows_correct]
  revert c carry
  decide

def CertificateObligations : Prop :=
  Data.states 0 = start ∧
  (∀ (i : Fin 8) (c : Column), transition Data.rows (Data.states i) c = Data.states (Data.edges i c)) ∧
  (∀ i : Fin 8, boundaryGood (Data.states i))

instance : Decidable CertificateObligations := by
  unfold CertificateObligations boundaryGood
  infer_instance

def checkCertificate : Bool := decide CertificateObligations

theorem certificate_accepted : checkCertificate = true := by decide

theorem certificate_obligations : CertificateObligations :=
  of_decide_eq_true certificate_accepted

theorem observation_all_lengths (xs : List Column) :
    boundaryGood (run (transition Data.rows) start xs) := by
  have h := certificate_obligations
  rw [← h.1]
  exact closed_certificate_sound (transition Data.rows) Data.states Data.edges 0
    boundaryGood h.2.1 h.2.2 xs

end QKF
