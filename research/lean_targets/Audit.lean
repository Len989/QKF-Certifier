import QKFTarget

/- The validation driver requires every listed theorem to occur, and rejects
any axiom outside propext/Quot.sound. Merely compiling this file is insufficient. -/
#print axioms QKFTarget.columns_complete
#print axioms QKFTarget.closed_certificate_sound
#print axioms QKFTarget.atom_numerical_step
#print axioms QKFTarget.numerical_formula_all_widths
#print axioms QKFTarget.cyclic_successor_all_widths
#print axioms QKFTarget.cyclic_extrema_characterization
#print axioms QKFTarget.Original.accepted
#print axioms QKFTarget.Original.numerical_all_widths
#print axioms QKFTarget.Irrelevant.accepted
#print axioms QKFTarget.Irrelevant.numerical_all_widths
