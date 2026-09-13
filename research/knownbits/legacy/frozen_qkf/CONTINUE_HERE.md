# Continue QKF from this snapshot

User goal: develop a broad, independently checkable reasoning architecture,
ultimately exploring replacement of current SMT machinery. The immediate
research question is which abstract transformers admit small constructive
semantic interfaces independent of word width. Do not equate unbounded-width
proofs for these fragments with a demonstrated general SMT replacement.

## Current completed result

* Pinned public QKF commit: `f93561682319e8b911ed32c01583f2a496dc59fc`.
* New research extension: `qkf-observer-identities-v1`.
* Corpus: 39 original MLIR solutions, 411 guarded components; fixtures included.
* Exactly compilable components: **124**, up from 102.
* Certified components: **82**, up from 70; 57 ordinary targets and 25 stronger
  unconditional modular obligations for flag families.
* Whole source proofs: **5/39: AND, OR, XOR, Smax, Umin**.
* Umin is **7/7**; actual SSA composition and actual meet semantics checked.
* All old 70 proofs retained. New 12 = 5 Umin + 7 outside Umin.
* All 24 source-validated counterexamples concern stronger flag-family targets.
* No state/transition-attempt budget exhausted.

Use `results/comparison.json`, `results/proofs.json`, and
`results/observer_audit.json` for exact IDs, costs, rule use, and residuals.
`README.md` gives complete reproduction and certificate-only commands. The
public GitHub release has not been modified by this research package.

## Mathematical advance

For H(n)=set_high_bits(0,n), L=countl_one, and any word-valued n,

`lshr(H(L(shl(x,n))),n) = H(L(x OR H(n))) AND NOT H(n)`.

The equality includes n=0 and n>=w. When n=L(y), the right side compiles
through two already supported high-run observers. A separate MSB-first
description needs three deterministic streaming states. The actual checker
still uses the previous LSB-first relation product; Umin component 6 has
116 invariant states, not three.

The other useful family is fixed terminal windows: clear_low_bits(x,w-k)
retains k high bits when w>=k. Current w>=2 rewriting enables k=0,1,2;
w=1 is checked separately on source. See `OBSERVER_PROOFS.md` for all twelve
rule families and checked side conditions.

The key shifted-mask rule and signed-max threshold rule are used only in
Umin/6 in this corpus. Outside gains come from other general rules. Do not
claim empirical multi-family use of the principal identity on this dataset.

## Next concrete target

Smin is a useful next full-solution target: **6/12 components already proved**.
The unresolved entries are 3, 4, 8, 9, 10, and 11. Remaining syntax includes
width-related masks/shifts, leading-zero counts, two multiplication nodes in
component 8, and a signed-division node in component 11. These are residual
expressions, not yet lower bounds or evidence that full operator relations
are needed. Inspect their actual guards and observations before choosing an
interface.

The next research pass should:

1. Derive exact observation-specific reductions for those six source entries,
   retaining all width boundaries and branch premises.
2. Seek reusable interface constructors for endpoint observations and fixed
   terminal windows; retain exact source-replay evidence for every reduction.
3. Certify the full source composition if all components close.
4. Apply the additions uniformly to all 411 components with the same targets
   and limits, reporting both new full solutions and component coverage.

Other ordinary target progress: Add 5/13, Sub 9/16, UaddSat 5/14, Umax 3/10,
UsubSat 6/16. In total 47 ordinary target components remain outside the
implemented candidate fragment.

## Keep the contracts straight

* The target registry is unchanged; unsupported target families are not proofs.
* `transfer.neg` is bitwise NOT. Arithmetic is modular; shifts/division are
  total under `total-transfer-words-v2`, not C undefined behavior.
* Flag preconditions and poison are not modeled. Stronger unconditional
  counterexamples are not upstream bug findings.
* Exact source-expression rewriting and target soundness are distinct claims.
* Certificates are source-bound, caller-target-bound closed invariants. The
  checker recomputes transitions and does not trust a search success label.
* Python kernels are trusted; new results have no Lean formalization yet.
* The invariant size is independent of w but may grow exponentially in the
  program or number of simultaneous observations.
* Preserve this snapshot when extending it. Previous code and fixtures have
  hashes in `PROVENANCE.json`; do not silently change baseline packages.
* `PAPER_III_INSERT.md` is prepared text, not an already published revision.
