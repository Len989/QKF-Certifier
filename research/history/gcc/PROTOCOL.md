# Frozen GCC external transfer experiment — protocol v1

Recorded locally before any QKF or SMT outcomes on these inputs. This is not
a third-party preregistration or a blind/statistically representative trial.

## Question and deterministic selection

Does the delivered compositional QKF core transfer to complete implementations
from a compiler source distinct from the LLVM and tnum development examples?
Source: GCC releases/gcc-15.2.0, exact commit
`5115c7e447fc07457443df874bf57840e8316d5f`, `gcc/tree-ssa-ccp.cc`.
Select all ordinary binary integer operations in `bit_value_binop` whose
concrete target is already supported: BIT_AND_EXPR, BIT_IOR_EXPR, BIT_XOR_EXPR,
PLUS_EXPR, MINUS_EXPR, MIN_EXPR and MAX_EXPR (each signed and unsigned).
Nine cases: gcc_and, gcc_or, gcc_xor, gcc_add, gcc_sub, gcc_umin, gcc_umax,
gcc_smin, gcc_smax. ADD/SUB and bitwise cases instantiate unsigned equal input
and output widths. MIN/MAX instantiate equal widths and their stated sign.
Unsigned saturation has no corresponding dispatch case here. Pointer aliases,
unary operations, shifts, multiplication, division, predicates, and rotations
are outside this target-aligned selection, recorded before measurement.
All nine selected cases stay in the denominator, including adapter failure,
unsupported, timeout, resource limit and counterexample. Simple bitwise cases
are controls; related carry formulas may overlap conceptually with development.
No claims that individual mathematical identities are new.

## Source and domain boundary

Retain exact upstream bytes/hash, selected source spans and license notice.
Inputs are nonbottom KnownBits pairs (Z,O), Z&O=0. GCC receives canonical
v=O, m=~(Z|O); m denotes varying bits. Result converts back via
Z=~(v|m), O=v&~m. All width bits of the result and every runtime branch in the
selected specializations are retained. GCC extensions to widest_int and the
source's fixed finite precision must be documented separately from the QKF
positive-width generalization. The certificate binds emitted SSA, not GCC C++.
No claim to certify the whole GCC pass, lattice wrapper, poison semantics,
precision conversion, arbitrary don't-care representatives, or entire compiler.

Validate source/body arithmetic independently and compare source-oracle outputs
to unrewritten SSA: exhaustive valid abstract inputs at widths 1..4; seed
20260912, boundary patterns plus 256 random pairs at widths 8,16,32,64.
Enumerate represented concrete pairs for widths 1..4. If a native shim is used
instead of GCC widest_int, identify it and do not call it actual GCC execution.
An adapter correction must be logged and affected checks repeated; no core fix.

## Frozen core, budgets and ablation

Use the exact 11 composition Python files in CODE_FREEZE.json, the 12 previous
research files and 11 public dependency files in baseline/FREEZE.json, plus
referenced transitive dependencies. Check hashes before and after.
No target, proof rule, relation node, search or normalization heuristic changes.
New infrastructure: source adapter, native shim, runners and result collection.
Fresh source parsing and all normalization searches count in production time;
do not reuse old traces. Full-case aggregate caps: 100000 states, 2000000
transition attempts, 60 seconds producer, 60 seconds separate replay,
512 leaves, branch depth 24. Isolate workers and save each outcome atomically.
Run composed and monolithic (source splitting disabled) on identical inputs,
budgets and fresh normalization. This is the predeclared composition ablation.
Replay certificates in a fresh process with proof-search entrypoints disabled.
Record producer/replay seconds, peak process RSS, states, transition attempts,
leaves, normalization counts, certificate sizes and complete failures.

## Fixed-width SMT comparison

Z3 4.15.3.0; raw, unnormalized same SSA and nonbottom input concretization.
Fresh solver, seed 20260912, 5000 ms solver limit at each width
1,2,3,4,8,16,32,64. Record encoding separately from solving, save SMT-LIB and
all sat/unsat/unknown outcomes. Independently evaluate any satisfying witness.
Check the SMT encoder against the unchanged word oracle on deterministic
samples. Eight finite obligations are not an all-width theorem; no headline
speedup between unequal guarantees, and plain UNSAT is not independent replay.
No post-outcome encoding choice or alternative solver run in the main result.

## Finish

Report all nine cases, empirical adapter boundary, exact/core source hashes,
raw outcomes, ablation and limitations. Classify refusals before considering a
new development version. Do not expand scope or rewrite paper III in this test.
Retain reproducible files and a concise Russian report, then deliver the stage.
