# Common source-to-target research run

The common entry point is `python -m research.observations.run` from a full
repository checkout with Python 3.10+. It needs no extra Python packages.
This is post-release research, not an extension of the installed `qkf` CLI.
The existing profile-specific commands and certificate schemas are unchanged.

## Supported combinations

| Explicit profile | Independently supplied goal | Existing checkers |
|---|---|---|
| `descending` | `maximum`, `bound` | `source_factor`, `property_kernel` |
| `ascending` | `cyclic_successor`, `membership` | `ascending_kernel`, `successor_kernel` |

The specification is one of the existing versioned, exact JSON templates.
A general specification language and composition of regions are not added here.
`verify` requires an explicit profile. At `check`/`explain`, the external goal
selects the profile; an optional `--profile` must agree with it. A package cannot
select a different profile or import a module of its own choosing.

## Ascending example

Use new output paths; existing files/directories are never overwritten.

```sh
python -m research.observations.run spec successor.goal.json \
  --profile ascending --claim cyclic_successor

python -m research.observations.run verify research/graal/native/IntegerStamp.java \
  --profile ascending --spec successor.goal.json \
  --output reproduction/common_successor_01

python -O -m research.observations.run check research/graal/native/IntegerStamp.java \
  --spec successor.goal.json \
  --package reproduction/common_successor_01/package.json

python -O -m research.observations.run explain research/graal/native/IntegerStamp.java \
  --spec successor.goal.json \
  --package reproduction/common_successor_01/package.json
```

For the descending maximum use the same commands with `--profile descending`
and a separately created `--claim maximum` specification. `bound` and
`membership` are weaker goals, not aliases for the stronger properties.

`spec` only writes a template. `verify` parses the supported source, runs its
source producer, checks the model, runs the independent target producer and
checks the final package. `check` performs no search. `explain` performs the same
full replay and adds the proof chain, preconditions, obligations and either
closure size or the checked counterexample. It never trusts a saved explanation.

## Outputs and acceptance

A complete verification writes `package.json` and `result.json` in a new directory.
An unsupported source or exhausted search writes only `result.json`, with no
proof package. I/O/input/internal failures do not produce an acceptance. If a
write is interrupted or fails, a partial directory may remain; use a new output
path. A malformed partial package cannot pass replay.

One JSON result is printed on stdout. Unexpected exception details go to stderr.
Accept a program property only when `verify` or `check` reports `certified`.
A successfully *checked refutation* deliberately exits nonzero.

| Status | Exit | Meaning |
|---|---:|---|
| `certified` | 0 | The external property has been checked in its stated profile |
| `refuted` | 1 | A concrete violation has been independently replayed |
| `budget_exhausted` | 2 | No complete property verdict and no package |
| `invalid_certificate` | 3 | Supplied package, binding, proof or cached result fails replay |
| `unsupported` | 4 | Source is outside the selected restricted frontend |
| `input_error` | 64 | Arguments, goal, profile conflict, budget, file access or output conflict |
| `internal_error` | 70 | Unexpected fault or a generated proof fails checking; never acceptance |
| `written` | 0 | Only `spec`: template written, not a proof |

A missing/unreadable package path is an input error. An accessible but malformed
package is an invalid certificate. Unsupported/altered specifications are input
errors: they are not interpreted as weaker contracts. A changed source supplied
for replay invalidates its package; it is not reported as a program refutation.

## Package contract

`qkf-research-package-v1` has exactly seven top-level fields:

```text
schema, profile, contracts, binding, dependencies, proofs, result
```

`proofs.source` and `proofs.property` embed the original certificates without
changing their schemas. There are no certificate-supplied file paths to follow.
The fixed dependency graph says that the source proof depends on the external
source, and the property proof additionally depends on that source proof and the
external specification. This is not yet a generic composition graph.

The bindings include the SHA-256 of exact UTF-8 source bytes and canonical-JSON
hashes of the external specification and both inner certificates. Source comments
and line endings are significant; JSON layout is not. Duplicate JSON keys and
non-finite JSON constants are rejected. Hashes bind content, not authorship.

Replay verifies the envelope, invokes the original source and property checkers,
and reconstructs `qkf-research-run-result-v1`. The saved result must agree exactly.
Changing only a summary, a scope flag or a hash does not produce a new theorem.
Tests also rebind a weak positive proof to a strong target and check rejection
at the original protected target obligations, not just at the outer hash gate.

Input transport limits are 2 MiB for source, 64 KiB for a goal/budget and 32 MiB
for a package. They do not restrict the width quantified in a checked theorem.
Inputs/outputs are local UTF-8/JSON files, not executable package code.

## Search budgets

Only `verify` accepts `--budget budget.json`. For example:

```json
{"source":{"max_states":64,"max_offset":255},"property":{"max_states":8192,"max_witness":256}}
```

That example is ascending-specific. An empty object selects all defaults.
Unknown keys, non-integers (including booleans) and out-of-range values are input
errors, not silently ignored options.

| Profile / stage | Configurable limit | Default | Allowed range |
|---|---|---:|---|
| ascending / source | `max_states` | 64 | 1..64 |
| ascending / source | `max_offset` | 255 | 0..255 |
| ascending / source | `max_observations` | 63 | 0..63 |
| ascending / source | `max_pullbacks` | 4096 | 0..100000 |
| ascending / source | `max_classes` | 64 | 1..64 |
| descending / source | `max_contexts` | 8 | 1..8 |
| descending / source | `max_actions` | 16 | 1..16 |
| both / property | `max_states` | 8192 | 1..8192 |
| ascending / property | `max_witness` | 256 | 1..256 |

Other frontend/factor limits and the descending witness limit remain inherited
from the original checkers/producers. These are search-size budgets, not a new
wall-clock or process-memory limiter. Replay uses the existing fixed checker
limits and cannot be weakened by a producer's budget file.

## Reproduce the complete existing population

```sh
# Fresh search, wrapping, replay and explanation for all 18 target cases.
python -m research.observations.run_unified_experiment reproduction/common_fresh_01

# Reconstruct the same envelopes from retained original proofs, without search.
python -O -m research.observations.run_unified_experiment reproduction/common_retained_01 --retained-only

python -m unittest discover -s research/observations/tests -p 'test_run*.py' -v
python -m unittest discover -s research/observations/tests -v
```

The experiment covers four descending sources with two goals and five ascending
sources with two goals: **18 property cases, 11 positive and 7 refuted**. These
are the old target cases, not 18 new programs. Each case directory contains its
external `source.java` and `goal.json` alongside `package.json`, `result.json`
and `explanation.json`; `SUMMARY.json` and `MANIFEST.json` record the run.

`--retained-only` uses fixed repository source paths and independently chosen
goals. Its inputs remain in `evidence/property`, `evidence/ascending` and
`evidence/successor`. Thus packages can be reconstructed after CI artifacts expire
without rerunning producers. The separate Unified research run workflow checks
Python 3.10 and 3.12, fresh/retained package identity and optimized command replay,
and retains the generated files as artifacts for 30 days.

## Scope and trusted components

A source-model certificate and a property certificate are still different claims.
The descending property concerns `seed | optional_subset`, disjoint initial
optional bits and `seed <= bound`; it does not establish arbitrary Graal caller
preconditions. The ascending property concerns a legal masked region entry and
only emitted payload bits, not the path into the loop or its full signed return.

The trusted implementation now additionally includes envelope/JSON validation,
profile dispatch and the common result assembly. It reuses rather than replaces
the restricted frontends, slice rules and explicit target rules. This step adds
no new Lean theorem, no whole `computeLowerBound` or `create` proof, no KnownBits
coverage and no general source-language support. Bounded native experiments in
the old CI remain separate from the mathematical width-independent certificates.
