# Typed target observations — run 2

This research extension is based on main
`8e482b2f2f7343af24a8c5a2e3a17867e3bd7ae7` (merged PR #5).
Full local source integration now passes on the uploaded base. See
`RUN2_REPORT_RU.md` for exact results and limitations. Complete publication to
GitHub and remote CI are still pending; the partial remote PR is not merge-ready.

## Use

From a full checkout with this patch applied, Python 3.10+:

```sh
python -m research.observations.run spec changes.goal.json --profile ascending --claim changes --language observations
python -m research.observations.run verify research/graal/native/IntegerStamp.java --profile ascending --spec changes.goal.json --output reproduction/typed_changes_01
python -O -m research.observations.run check research/graal/native/IntegerStamp.java --spec changes.goal.json --package reproduction/typed_changes_01/package.json
python -O -m research.observations.run explain research/graal/native/IntegerStamp.java --spec changes.goal.json --package reproduction/typed_changes_01/package.json
```

All output paths must be new. Omitting `--language observations` keeps the old
fixed-template specification and v1 package route. Existing certificate schemas
and source/property checkers are not rewritten. `verify` requires the profile;
`check`/`explain` derive it from the independently supplied external specification.

## Specification

A goal has exactly six fields:

```json
{
  "schema": "qkf-word-observation-spec-v1",
  "profile": "ascending",
  "domain": "legal-masked-entry-v1",
  "quantifier": "forall_legal_alternative",
  "preconditions": [["ne", "must", "may"]],
  "obligations": [
    ["subset", "must", "output"],
    ["subset", "output", "may"],
    ["ne", "output", "seed"]
  ]
}
```

This `changes` formula asserts legal output distinct from the seed when the mask
has an optional bit. It is not a new specialized checker: it uses the same
predicate compilation and closure algorithm as the four translated old goals.
A template name is never an input to the generic checker.

Word terms are declared variable names, `zero`, `ones`, or lists headed by
`bit_not` (unary), `bit_and`, `bit_or`, `bit_xor` (binary). `ones` is the all-ones
word of the current payload width, not the integer literal 1. No shifts, counts,
arithmetic terms, memory, signed order, or source-language code occur in this
version of the target grammar.

Predicates: `eq`, `ne`, `ult`, `ule`, `ugt`, `uge`, `subset`, `disjoint`.
Both predicate arguments are word terms of the same width. Formula connectives
are `not`, `and`, `or`, `implies`, and JSON Boolean constants. `and`/`or` take
2–16 operands. The precondition list is conjunctive; the obligation list is
conjunctive under those preconditions.

Preconditions may reference inputs, not `output` or `alternative`. The source
profile and universal alternative domain cannot be replaced by a formula.
Additional input preconditions are explicit, hash-bound user assumptions.
Satisfiability of those assumptions is **not certified**. A false precondition
can yield a vacuous conditional theorem, and is shown as such in the result;
the result is not relabeled as an unconditional legacy maximum/successor claim.

The result claim is `word_observation_formula` and includes the external goal
fingerprint and formulas. A new `qkf-research-package-v2` envelope contains the
unchanged source certificate plus `qkf-word-observation-property-v1`.
Old external specification schemas still select v1, not implicit conversion.
`target_templates.from_legacy` is the explicit, separately tested translation.

## Fixed domains and source interfaces

Ascending: positive width, words in `[0, 2^w)`, must subset seed subset may.
The independently quantified alternative has the same mask membership. Columns
are `(must, may, seed, alternative)`, six choices. The checked source transducer
provides output bits; the target may not assume they satisfy membership.

Descending: positive payload width and the old extra zero-sign-bit contract,
optional = may & ~must, seed & optional = 0. The alternative is any word
`seed | s` for a submask `s` of optional. This does NOT silently assume that seed
contains all must bits. The upper-bound condition is an explicit input formula.
The new 32-column alphabet is `(bound, must, may, seed, output, alternative)`;
output is unrestricted. The checked source graph rejects non-source traces.
A projection absent from its alphabet enters a rejecting sink, never an
accepting state or an assumed target obligation. The two source interfaces
are intentionally not identified with one another.

A nonempty-word bit in the joint state distinguishes the mathematical theorem's
positive-width domain from the empty initialization. In particular, the formula
`ones != zero` must not be incorrectly refuted at width zero.

## Certificate argument and trust

`target_syntax` derives the questions syntactically and shares repeated identical
questions (including `<`/`<=` on the same ordered pair). No minimum question
count, minimum state count or asymptotic search improvement is claimed.

Coordinatewise word terms have their bit semantics by structural induction.
Equality, support inclusion and disjointness accumulate conjunctions over bits.
For order, a new unequal higher bit dominates every possible lower difference;
otherwise the previous comparison is retained. Boolean composition therefore
preserves the whole-word interpretation of every goal formula.

The producer proposes a closed carrier or a concrete counterexample. The
checker recompiles the entire observation program from the external goal and
checks its equality to the supplied program. It verifies typed initial/parent
states, all column transitions, source acceptance and target obligations.
Induction covers every positive-length trace of the declared source model;
the independent competitor alphabet supplies universal quantification.

Negative results are replayed through the source factor, a whole-integer source
interpreter, and a separate direct integer formula evaluator. None of those
replays imports the target producer. The finite closure method is standard.

The source frontend, slice semantics, typed compiler and target arithmetic rules
remain trusted implementations. This is not a whole-JVM theorem, a Lean proof,
source-region composition, or a new installed `qkf` feature. The global source
observation-inference problem is not solved by adding this target grammar.

## Limits and validation commands

Target grammar limits: 512 syntax nodes, nesting depth 16, 16 distinct observation
questions, up to 16 preconditions and 16 nonempty obligations. Exceeding these
fixed schema limits is an input error. Search has explicit inherited budgets:
up to 8192 joint states and 256 witness columns. Exhaustion returns no package.
The common JSON/file limits, status codes and no-overwrite behavior are retained.
There is no new wall-clock or memory process limit and no general polynomial
complexity claim.

The complete source regression reproduced locally is:

```sh
python -m unittest discover -s research/observations/tests -v
python -m research.observations.run_target_experiment reproduction/typed_targets_01
python -O -m research.observations.run_target_experiment reproduction/typed_targets_01 --replay
```

The experiment saves complete packages, exact sources, independent goals,
explanations, a summary and a manifest. Replay reconstructs the intended goals
from the fixed case selection instead of trusting a package's target choice.
The 18 translated old cases and 5 `changes` cases have separate denominators;
they are not 23 new source programs. The proposed CI runs on Python 3.10/3.12.
Its presence in this patch is not a claim that CI has already passed.

All 23 complete source/goal/proof packages are retained under
`research/observations/evidence/typed_targets`. No search is needed to replay:

```sh
python -O -m research.observations.run_target_experiment research/observations/evidence/typed_targets --replay
```

The evidence tests independently reconstruct goals, replay every inner proof,
check copied sources/results and the manifest, reject rehashed corrupted proofs,
and replay all 23 packages in fresh processes with producer, template, legacy
target-kernel, solver and native-harness imports blocked. The snapshot does not
choose a weaker goal for the checker.
