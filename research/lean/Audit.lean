import QKF

#check QKF.forced_sound
#check QKF.forced_no_conflict
#check QKF.atoms_force_row
#check QKF.source_phase_factor
#check QKF.forced_rows_correct
#check QKF.certificate_accepted
#check QKF.observation_all_lengths
#check QKF.mask_successor_all_widths
#check QKF.source_word_factor
#check QKF.word_width

/- These guards make an unexpected change of proof assumptions a build error. -/
/-- info: 'QKF.forced_sound' does not depend on any axioms -/
#guard_msgs in
#print axioms QKF.forced_sound
/-- info: 'QKF.atoms_force_row' does not depend on any axioms -/
#guard_msgs in
#print axioms QKF.atoms_force_row
/-- info: 'QKF.source_phase_factor' depends on axioms: [propext] -/
#guard_msgs in
#print axioms QKF.source_phase_factor
/-- info: 'QKF.forced_rows_correct' depends on axioms: [propext] -/
#guard_msgs in
#print axioms QKF.forced_rows_correct
/-- info: 'QKF.certificate_accepted' depends on axioms: [propext] -/
#guard_msgs in
#print axioms QKF.certificate_accepted
/-- info: 'QKF.observation_all_lengths' depends on axioms: [propext] -/
#guard_msgs in
#print axioms QKF.observation_all_lengths
/-- info: 'QKF.mask_successor_all_widths' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in
#print axioms QKF.mask_successor_all_widths
/-- info: 'QKF.source_word_factor' depends on axioms: [propext] -/
#guard_msgs in
#print axioms QKF.source_word_factor
