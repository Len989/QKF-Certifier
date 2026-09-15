# Run 4 standalone formal-validation branch

This branch publishes the new Lean project from the local run-4 candidate on top of main after PR 5. It does not silently publish or merge runs 2 and 3, and it does not claim their complete CI acceptance. The mathematical project is standalone: its explicit inputs are the finite source machines and closed observation certificates in `QKFTarget/Exported.lean`.

The exported tables were locally generated from checked run-2 source/goal packages for the original ascending region and the irrelevant-register variant. The source parsers, slice rules, Python runtime, and full Java helper are outside the Lean theorem. Positive numerical results concern the explicit machine and the fixed independently named successor formula, not arbitrary Java programs.

Initial publication is a candidate. A build must actually run before any formal acceptance is claimed. Axiom audit and negative controls will be recorded separately from historical CI. Main and the existing `research/lean` pilot are unchanged.
