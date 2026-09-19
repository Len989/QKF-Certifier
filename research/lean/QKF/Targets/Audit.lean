import QKF.Targets.Checked

/- Exact axiom sets are enforced by the kernel-checked build. -/
/-- info: 'QKF.Targets.atom_snoc' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in
#print axioms QKF.Targets.atom_snoc

/-- info: 'QKF.Targets.accepted_all_widths' depends on axioms: [propext, Quot.sound] -/
#guard_msgs in
#print axioms QKF.Targets.accepted_all_widths

/-- info: 'QKF.Targets.cyclic_successor_all_widths' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in
#print axioms QKF.Targets.cyclic_successor_all_widths

/-- info: 'QKF.Targets.original_accepted' depends on axioms: [propext] -/
#guard_msgs in
#print axioms QKF.Targets.original_accepted

/-- info: 'QKF.Targets.original_cyclic_successor' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in
#print axioms QKF.Targets.original_cyclic_successor

/-- info: 'QKF.Targets.irrelevant_cyclic_successor' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in
#print axioms QKF.Targets.irrelevant_cyclic_successor

/-- info: 'QKF.Targets.original_singleton' depends on axioms: [propext, Classical.choice, Quot.sound] -/
#guard_msgs in
#print axioms QKF.Targets.original_singleton
