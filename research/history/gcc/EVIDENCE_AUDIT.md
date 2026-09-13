# Independent inspection of recorded QKF evidence

This audit reads the frozen files, completed result JSON, certificates and source
code. It does not rerun proofs, solvers, native checks or certificate replay.

## Supported conclusion

The records support **9/9 source-bound SSA soundness certificates at every
positive word width**, in both composed and monolithic modes. All 18 verdicts
have a separate fresh-process replay record, with seven search entry points
disabled and neither `branch_producer` nor Z3 loaded. Structural inspection of
the 18 certificates found matching source hashes, targets, entry `solution`,
width partition, certificate hashes, and nine width-one abstract-input rows.
Certificate invariant sizes, branch counts and leaf counts agree with the
producer summaries and replay records. This is evidence inspection, not an
additional independent implementation of the proof checker: the frozen Python
checker and its semantic lemmas remain trusted.

All 69 file hashes in `FREEZE.json` and all seven file/result hashes in
`INFRASTRUCTURE_FREEZE.json` match the files inspected. Both mode summaries
report the unchanged 34 relevant core/dependency Python files. Initial,
normalized and observed expression hashes agree between the two modes for each
case. The runner generates normalization from each actual input source and does
not load historical expressions or traces.

## State-accounting defect and its effect on this experiment

The frozen `branch_producer.py` increments `totals['states']` only after a
successful invariant. States discovered in failed, weakened-guard trials are
not charged cumulatively against the 100000-state cap. Therefore the generic
implementation does **not** enforce the protocol's full accumulated search-state
cap exactly as written. No core change or repeated experiment was made here.

For these completed cases the full trial counts can be recovered exactly:
`regular_interfaces.discover` reports `state_count = len(states)` on success and
`states_explored = len(states)` on a counterexample, including discovered states
still waiting in the queue. Every saved trial ended normally. Summing these
counts across every guard trial, counting repeated states in different trials
again, gives:

| Case | Composed certificate states | Failed-trial states | Composed all-trial states | Monolithic all-trial states |
|---|---:|---:|---:|---:|
| gcc_and | 2 | 0 | 2 | 2 |
| gcc_or | 2 | 0 | 2 | 2 |
| gcc_xor | 2 | 0 | 2 | 2 |
| gcc_add | 5 | 0 | 5 | 5 |
| gcc_sub | 5 | 0 | 5 | 5 |
| gcc_umin | 51 | 36 | 87 | 100 |
| gcc_umax | 51 | 36 | 87 | 100 |
| gcc_smin | 476 | 166 | 642 | 1064 |
| gcc_smax | 476 | 166 | 642 | 1064 |
| Total across nine cases | 1070 | 404 | 1474 | 2344 |

Thus **no observed case exceeds the intended 100000-state cap**, even when all
failed trials are included. The largest complete per-case sum is 1064. The
defect affects the general budget-enforcement claim, not these proof verdicts
or the eligibility of these particular runs. Report 1070 as certificate states,
and 1474 as accumulated discovered-state counts over all composed trials.

Transition attempts are handled differently and correctly: the producer charges
every trial in a `finally` block. The sums of all saved trial attempts agree
exactly with the full-case summaries: 37602 composed and 73648 monolithic. Replay
`transitions` counts accepted semantic transitions checked in the final
invariants; it is not the same quantity as producer attempts, which include
invalid guesses and failed trials. The last progress snapshot can precede the
final successful state increment; use final records for final totals.

## Composition comparison

| Metric, total across the nine cases | Composed | Monolithic |
|---|---:|---:|
| Source-bound certificates replayed | 9 | 9 |
| Certificate invariant states | 1070 | 2344 |
| States discovered, summed across all trials | 1474 | 2344 |
| Transition attempts, all trials | 37602 | 73648 |
| Certificate bytes | 121897 | 181055 |
| Producer seconds | 2.1023 | 3.8620 |
| Replay seconds | 0.6764 | 2.5655 |
| Producer plus replay seconds | 2.7786 | 6.4275 |

Composition improves resource use on the four min/max cases, not coverage in
this corpus. The five other cases have no source split and identical invariant
sizes and attempt counts. Resource ratios over all nine cases are about 1.96
for attempts, 2.19 for certificate states, and 1.59 for states discovered over
all trials. The recorded combined time ratio is 2.31. These are descriptive
ratios from one run, not estimates from repeated controlled timing trials.
Reported stage times include fresh parsing/normalization and certificate work;
they exclude process startup, imports and integrity-check overhead.

Every case has zero observer rewrites, zero bounded-mask rewrites and zero
low/high run nodes. This corpus tests transfer of the existing arithmetic and
Boolean relation machinery and source branch composition. It does not add
external evidence for the bounded-count-mask mechanism itself.

## Source and quantification boundary

The all-width theorem binds the emitted full `solution` SSA under the specified
total word semantics and nonbottom KnownBits inputs. It is not an all-width
machine-checked equivalence theorem between GCC C++ and that SSA, nor a proof
about an actual GCC build or its complete pass. The native comparison executes
verbatim selected C++ bodies with a labelled local `__int128` arithmetic shim;
it does not execute GCC's `widest_int` implementation. `ADAPTATION_AUDIT.md`
supplies the separate manual width-reduction argument and its restrictions.

The saved differential checks cover 66420 abstract-input pairs exhaustively at
widths 1–4, 629136 represented concrete pairs there, and 25092 source/SSA pairs
at widths 8, 16, 32 and 64. These are finite empirical checks of the adaptation;
they must not be relabelled as proof of the adaptation for arbitrary widths.
The selected canonical equal-width integer specializations, the manual source
argument, and the fixed finite precision of GCC remain the explicit boundary.

Likewise the eight fixed-width SMT obligations per case have different
quantification from a positive-width QKF certificate. A solver `unknown` is no
counterexample; an `unsat` result is not independent certificate replay. No
headline QKF/Z3 speedup claim follows from comparing those unequal guarantees.

The nine cases are a deterministic target-aligned selection from another
compiler source, including simple controls and related arithmetic formulas.
They provide an encouraging transfer result, not a representative or blind
measure of general SMT replacement.

## Final SMT record reconciliation

A final read-only inspection confirms `results/smt/smt_results_reconciled.json`
has `complete: true` and all **72 UNSAT** outcomes: nine cases at the eight
predeclared widths. Its entries exactly match the 72 individual saved records,
in protocol order, with no duplicate case/width pair. Every saved query SHA-256
and every frozen execution fingerprint matches. `results/FINAL_SUMMARY.json`
uses these authoritative individual records.

The original `results/smt/smt_results.json` remains preserved with
`complete: false` and 71 entries. The reconciliation record documents this
aggregate-file incident; its cause was not established. The missing aggregate
entry was recovered from its already saved individual record, with no solver
rerun or encoder change. The final aggregate wall-clock total was not recovered:
9.7855 seconds is the sum of the 72 recorded subprocess durations, while 1.5837
seconds is the sum of solver-check times. Neither is a recovered complete-run
wall-clock measurement. These 72 finite-width UNSAT results retain the
quantification limitations stated above.
