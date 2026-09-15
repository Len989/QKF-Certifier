# Source-bound masked-ceiling composition

This extension composes the published typed-target route (PR #11) without
changing its source or target checkers. The caller supplies a small typed JSON
wrapper, two exact source texts, and an independent versioned ceiling goal.
It is not the original Graal `computeLowerBound` wrapper, and is not a new Lean
theorem or a general Java control-flow verifier.

## Contract

For positive payload width `w`, compatible masks `must subset may`, and
`0 <= bound, must, may < 2^w`, let

```
L = {x in [0, 2^w): (x & must) == must and (x & ~may) == 0}.
```

Return `Value(y)` exactly when `L` contains a word at least `bound`, with `y`
the smallest such word. Otherwise return `Empty`. This is a tagged result:
`Value(0)` is not an empty marker. For `must=0, may=5`, the legal words are
`0,1,4,5`: bound `2` gives `Value(4)`, bound `6` gives `Empty`.

The example returns `must` below the minimum and `Empty` above `may`. Inside
that range it runs the certified descending maximum from seed `must`. If the
result equals the bound, it returns that result; otherwise it invokes the
certified cyclic successor with that exact result and the same masks.

## What the composition checker establishes

The JSON program is the actual wrapper input, not an instruction to substitute
a hard-coded example. Its grammar has comparisons of live words, branches,
tagged returns, and at most one static call per region role. It has no loops,
paths, imports, arbitrary host code, side effects, or arithmetic. There are at
most six live order labels including an independently quantified competitor.

Positive certificates first check BOTH exact, independently fixed typed goals:
masked descending maximum and cyclic successor. A model-only proof, a weaker
bound/membership goal, or a target with added assumptions is not sufficient.
The descending carrier `seed | submask(may & ~must)` equals `L` at `seed=must`;
this identity and the minimum/maximum of the mask set are stated mathematical
rules, not properties inferred merely from the two numeric endpoints.

The checker enumerates every weak order of the wrapper inputs, call results
and legal competitor. For the original example there are 4,683 total preorders
on six labels, of which 1,076 satisfy the necessary mask-extrema inequalities.
These are order/equality cases, not concrete bit assignments; realizability of
every order is NOT assumed. Every real execution is represented, and impossible
cases may be eliminated by checked call contracts. Mask membership is tracked
separately from order, using provenance and equality of word values.

At a call, shared masks, entry membership and the floor's seed/nonempty premise
must hold. After the successor is known legal, it also instantiates the earlier
universal maximum contract. This rules out returning a legal successor below
the bound. At every return, membership, lower bound, minimality against the
arbitrary legal competitor, or exact emptiness is checked. Finite order-case
coverage plus the universal region contracts covers all positive mathematical
payload widths; testing a few widths is not the proof.

A failed abstract case or region lemma is not a program refutation. Negative
certificates require a concrete valid input, the actual wrapper trace, agreement
of whole-integer source execution with both checked source factors, and an
independent numerical target violation. Without one, the producer returns
`unresolved` or `budget_exhausted`, never a counterfeit counterexample.

Trusted components remain the restricted frontends/slice semantics, typed goal
rules, mask-carrier identity/extrema, JSON interpreter, and order-case bridge.
This does not prove signed JVM semantics, all of `computeLowerBound`, or
`IntegerStamp.create`. The source identity and primitive support of PR #9 are
preserved. The accepted Lean project is unchanged; its CI is regression only.

## Use from a clean checkout

Python 3.10+ and the standard library suffice for creation/replay. Use new output
paths. Java is needed only for the separate bounded native experiment.

```sh
python -m research.observations.composition_cli verify \
  research/observations/composition_example.json \
  --descending-source research/graal/native/IntegerStamp.java \
  --ascending-source research/graal/native/IntegerStamp.java \
  --spec research/observations/composition_goal.json \
  --output reproduction/ceiling_01

python -O -m research.observations.composition_cli check \
  research/observations/composition_example.json \
  --descending-source research/graal/native/IntegerStamp.java \
  --ascending-source research/graal/native/IntegerStamp.java \
  --spec research/observations/composition_goal.json \
  --certificate reproduction/ceiling_01/certificate.json
```

`explain` has the same arguments as `check` and rechecks the proof. `example` and
`spec` write templates, not theorems. `run` executes one concrete input given
`--models` and `--input`; its `executed` result is not a universal proof.
Exit codes: certified 0, checked refutation 1, exhausted 2, invalid certificate 3,
unsupported source 4, unresolved 5, input error 64, internal error 70.

## Reproducible constructed experiment

```sh
python -m research.observations.run_target_experiment reproduction/ceiling_targets_01
python -m research.observations.run_composition_experiment reproduction/ceiling_proofs_01 \
  --typed-evidence reproduction/ceiling_targets_01 --native --max-width 6
python -O -m research.observations.run_composition_experiment reproduction/ceiling_proofs_01 \
  --typed-evidence reproduction/ceiling_targets_01 --replay
```

The experiment consumes those freshly generated packages, not a hidden fallback
to old saved proofs. Exact source/goal identity and dependency fingerprints are
recorded and rechecked. Omit `--native` when a JDK is unavailable.

The 17 designed controls comprise 10 wrappers and 7 source changes. Expected
outcomes from the archived run-3 experiment are 3 certified, 13 refuted, and
1 unresolved (strict descending comparison). They are not external coverage.
The unresolved row includes 1,554 tested inputs at widths 1..4, no proof, and no
claim that the program is correct or incorrect at every width.

`evidence/composition/BASELINE.json` retains only canonical regression digests.
It is explicitly NOT a certificate. Full certificates, inputs, explanations,
manifest, dependency provenance and native summaries are saved in the selected
output directory and retained as CI artifacts for 30 days. Download them for
long-term retention or regenerate them with these commands. No unavailable file
from the conversation is needed. The 16 certificates are independently replayed
BEFORE comparison with the baseline; matching a hash cannot establish a theorem.

The unchanged mathematical core and 33 previous non-evidence tests are retained;
3 artifact tests now explicitly generate temporary full fixtures, then replay in
fresh processes with producer/SMT/native imports forbidden. Seven additional
integration tests cover fresh dependencies, rehashed corruption/provenance,
primitive transfer and non-acceptance of an unresolved report.

The `Composed masked ceiling` CI runs Python 3.10/3.12 and Java 17. It requires
55,986 exhaustive inputs (widths 1..6), 360 additional mathematical inputs up to
4096 bits, 56,196 physical inputs at widths at most 62, and all 13 native
negative witnesses. Repeating a population on two Python versions is not new
coverage. Workflow configuration alone is not evidence of a successful run;
actual final-commit outcomes are recorded in the PR discussion/artifacts.
