# Automatic finite observation inference

This research prototype derives an observation interface from a finite native
cell model and its declared output/terminal consumers. It does not receive a
partition, a desired number of classes, or a catalog of carry observations.

The latest [source observation stage](SOURCE_REPORT_RU.md) also derives the
initial comparison questions and shared-context wiring from a restricted Java
helper, before the finite model is built. Its arithmetic replay covers all
integers; actual Java execution is a separate bounded validation.

The [ascending source stage](ASCENDING_REPORT_RU.md) adds a second operation
family. It derives residual integer offsets and Boolean registers from an
exact Java loop region, then uses the same observation/forced-row checker.
The original gives 3 states and 2 classes; adding an irrelevant register gives
6 states and the same 2 classes. A larger source addition discovers offset 2
without a preset carry alphabet. This certifies the region's payload model,
not its surrounding helper or a separately specified successor property.

The first application reads only `require` and `source_cell` from the existing
Graal carry model. Reachable physical states are enumerated from the initial
state. The old `PHASES`, `quotient`, `source_quotient`, proof producer, and saved
certificates are not used. The original three states are automatically mapped
to two observational classes. Changing the forbidden-bit repair from add to
clear requires three classes, with a two-cell separating context.

## Run

From the repository root, with Python 3.10+ and no additional packages:

```sh
python -m research.observations carry reproduction/observations_carry
python -O -m research.observations check-carry reproduction/observations_carry/certificate.json
python -m research.observations.run_experiment reproduction/observations_experiment
python -m unittest discover -s research/observations/tests -v
```

Output directories must be new. `carry` saves the native model, the derived
certificate, and its checked result. `check-carry` rebuilds the model from pinned
repository source; it does not trust the model bundled next to a certificate.

For a different independently supplied finite model:

```sh
python -m research.observations derive model.json certificate.json
python -m research.observations check model.json certificate.json
```

In generic mode the model is the caller's trusted specification, not a theorem
that a JSON table represents some external program. Certificates contain no code.
Exit codes: 0 for certified, 1 for rejected/error, 2 for exhausted producer budget.
The API producer returns `candidate`; only checker replay returns `certified`.

## Construction

1. Seed questions from observed native output labels and terminal labels.
2. Pull questions back through native transitions. Add a question only when it
   splits an atom of the current Boolean observation algebra.
3. Stop at closure, producing the kernel of the derived question family.
4. Supply native atomic cells of each guarded backward row. Complete the row
   through explicit union/intersection steps, retaining its table and kernel.
5. Reconstruct output and next-class actions from these completed rows.
6. Provide concrete separating contexts for every pair of different classes.

The independent checker validates source binding, question derivations, the
partition, local stability, protected labels, native atoms, every forced cell,
row kernels, row-based transitions, the initial class, and separating contexts.
It does not import the producer or use SMT. Validation remains active under `-O`.

## Scope and theory

Certification means that the quotient preserves the declared observations of
this finite deterministic model for every finite symbol trace. It also certifies
that no two of its classes can be identified while preserving those observations.
For a generic model this includes all supplied states; the carry adapter supplies
only states reachable from its declared start.

For the carry experiment the consumer observes emitted nonsign bits. It does not
observe final physical carry or the `incremented` flag. No signed-bound theorem,
full Java source proof, or newly formalized Lean theorem is claimed.

The connection to [Paper I](https://doi.org/10.5281/zenodo.22736397) is explicit
completion of guarded preimage rows from labeled atoms. Here the atoms generate
the entire powerset carrier: this experiment does not enlarge a forced domain
beyond the generated subalgebra. A one-element quotient supplies the empty cell
explicitly because two distinct atoms are unavailable to force it by intersection.

Backward closure and finite behavioral equivalence are established algorithmic
ideas, not new theorems attributed to QKF. The change is an executable bridge
from the existing native cells to automatically selected, labeled observations
and replayable forced rows. See [the research report](REPORT_RU.md).

The [Paper II](https://doi.org/10.5281/zenodo.22736558) distinction between a
missing observation and a missing equality proof motivates future symbolic work.
This prototype evaluates finite sets exactly. Its separating-word length is
operational context depth, not Paper II's term-depth proof horizon.

Limits: at most 64 native states, 32 symbols, 16 output labels and 8 quotient
classes in the complete-row encoding. The atomic encoding below permits up to
64 quotient classes. Complete row tables are exponential in the number of quotient classes.
Producer budgets are explicit and exhaustion yields no certificate. The source
stages below support vocabulary and variable-identity discovery in two narrow
profiles. General source languages, incomplete native tables and arbitrary
width-parametric symbolic closure remain open.

## Derived shared-context observations

The [descending experiment](CONTEXT_REPORT_RU.md) now takes local partial
context transitions and constructs the reachable residual observation, without
using the old handwritten P update or sweep state table. Native singleton
preimages supply 72 cells; union/intersection proofs force 120 further cells.
The resulting 24 rows generate 15 reachable states and 120 transitions.

An automatic product search tests a specific weakening: replace every nonempty
residual by the full context carrier before the next local step. It finds a
two-bit trace accepted by the weakened interface and rejected by the exact one.
The checker validates the conflicting cut membership. This demonstrates that
this erasure is unsound; it does not prove that all 15 states are necessary.

```sh
python -m research.observations.context_cli descending reproduction/context_one
python -O -m research.observations.context_cli check-descending reproduction/context_one/certificate.json
python -m research.observations.run_context_experiment reproduction/context_experiment
```

Generic mode accepts an independently supplied finite local-constraint model:

```sh
python -m research.observations.context_cli derive context_model.json context_certificate.json
python -m research.observations.context_cli check context_model.json context_certificate.json
```

The generic model declares a finite context carrier, forward control, partial
functions from an upper cut to the adjacent lower cut, a bottom set and a top
boundary. The producer derives reachable pairs of control and residual set.
The checker establishes exact acceptance for every finite word of these supplied
constraints. Nonfunctional relations are rejected: unrestricted existential
preimages would not preserve the intersections used by these row proofs.

The descending adapter supplies the three comparison values, suffix comparison
control, column encoding and shared-cut wiring. It extracts only
`require/compare/prefix/select` from pinned `graal/previous/row_kernel.py`.
Neither `atom`, the old P observer, the sweep producer nor saved certificates
are executed. It still does **not** infer this vocabulary or wiring from Java.

`evidence/context/` contains the original and strict-guard variant, both compared
against a direct unsigned integer loop on all 37,448 legal column words of
widths 1–5. This finite comparison does not establish an all-width Java theorem.
The shared-cut checker runs without producer/SMT imports, including under `-O`.
Its tests also enumerate whole cut assignments for 100 random models, perform
40 context/control/symbol renamings and reject 18 certificate mutations.

Limits: 8 native contexts, 16 controls, 32 symbols, 4,096 residual states and
65,536 product-search states. Complete rows are exponential in the context
carrier. Exhaustion of either search budget returns no certificate. A missing
counterexample is not independently certified as an equivalence result.

## Minimal consumer factor of the residual observation

The [factor report](FACTOR_REPORT_RU.md) connects the two earlier stages into one
checked chain. The bridge first verifies the local-context certificate, then
rebuilds its residual model with the declared terminal consumer. Existing
question closure derives the coarsest stable factor. The default consumer
observes membership of the native top boundary; additional context queries may
be declared, but that boundary may not be silently removed.

For the descending model the result is **15 reachable residual states to 10
minimal classes**, with five generated questions, six equivalent-state pairs
and 45 separating class pairs. All separators have length at most one. The
result also recovers the entire allowed-context set from each class. This extra
recovery is checked from the actual blocks and is not assumed for other models.
Changing `<=` to `<` changes which comparison states merge.

The new atomic row encoding stores native singleton images, the justification
of the empty cell, a finite-union completion rule and a kernel projection.
Disjoint atom images establish intersection preservation. A row kernel is
equality of subsets after projection to atoms with nonempty images. Thus the
factor's eight rows need 80 supplied cells instead of enumerating 8,192 table
positions. The 8,112 forced consequences are logical counts, not executed or
stored proof steps. No powerset is expanded by this encoding.

```sh
python -m research.observations.factor_cli descending reproduction/factor_one
python -O -m research.observations.factor_cli check-descending reproduction/factor_one/certificate.json
python -m research.observations.run_factor_experiment reproduction/factor_experiment
```

Generic factor derivation and replay:

```sh
python -m research.observations.factor_cli derive context_model.json factor_certificate.json
python -m research.observations.factor_cli check context_model.json factor_certificate.json
python -m research.observations derive finite_model.json atomic_certificate.json --row-encoding atomic
```

`context_factor.Runner` validates the complete chain once and then executes the
80 factor transitions without storing the old residual control/mask state.
`context_factor.explain` derives merge obligations, question definitions, class
signatures and separating contexts from the checked chain. The checker
reconstructs the bridge model; a bundled `*.consumer.json` is only an inspection
artifact and is not trusted by source-bound replay.

`evidence/factor/` includes original, strict-guard and all-context-query
experiments. Each agrees with unsigned integer execution on all 37,448 legal
column words of widths 1–5. Tests additionally cover 80 random context factors
against a pair-state equivalence oracle, 20 complete semantic renamings,
30 compact-versus-complete row models, 17 certificate mutations, a 12-class
example beyond the old dense limit and fresh full-chain replay with
producer/SMT imports blocked under normal Python and `-O`.

The chain currently accepts at most 64 residual states and 64 factor classes.
Earlier context-state and question-search budgets still apply. Exhaustion
returns no chain certificate. Minimality is relative to the supplied finite
model and consumer; it is not a new theorem about arbitrary Java programs.

## Initial vocabulary and shared slices from Java source

`java_words` reads the actual `setOptionalBits` helper in
`research/graal/native/IntegerStamp.java`, checks its descending single-bit OR
shape and binds the implementation of its `CodeUtil.mask` primitive. It extracts
the input identities, comparison predicates, write footprint and legal columns.
The old comparison adapter is not imported. The parser retains Java literal
types, so an int shift cannot impersonate the accepted long shift.

For a word difference `d`, appending bits gives `2*d + a - b`. Pulling a source
question `d <= t` back gives `d <= floor((t - a + b)/2)`. Closing those questions
derives a finite interval observation over all integers. The independent
checker validates entire affine interval images, protected predicate labels,
and a supplied closed family of suffix transformations. The latter is derived
by composition, without a predefined less/equal/greater suffix vocabulary.

| Source guard | Context values | Suffix actions | Residual states | Minimal factor classes |
|---|---:|---:|---:|---:|
| `trial <= bound` | 3 | 3 | 15 | 10 |
| `trial <= bound + 1` | 4 | 6 | 27 | 13 |
| `trial <= bound + 3` | 6 | 13 | 62 | 20 |
| `trial <= initialValue` | 3 | 1 | 4 | 2 |

The last row derives equality of both lower input slices from their source
identity. Both the alphabet and the reachable suffix actions become smaller.
Context rows now support the same compact atomic completion principle as factor
rows. The complete row encoding remains available and is still the default of
the generic context API; this source pipeline explicitly selects atomic rows.

```sh
python -m research.observations.source_cli java reproduction/source_one
python -O -m research.observations.source_cli check-java reproduction/source_one/certificate.json
python -m research.observations.source_cli derive modified.java source_certificate.json
python -m research.observations.source_cli check modified.java source_certificate.json
python -m research.observations.run_source_experiment reproduction/source_experiment --native
```

Only the last command needs Java 17+; certificate replay needs Python alone.
`evidence/source/` retains all four sources, extracted IRs, models, certificates,
factor explanations, execution results and validation logs. The experiment
checks 113,708 legal column words and 28,353 concrete native helper calls across
the four variants at payload widths 1–5. Inputs are column representatives,
not exhaustive enumeration of the helper's four word parameters.

The trusted source front end still contains the accepted loop skeleton and
generic arithmetic/slice rules. It supports one immutable comparison word,
six comparison operators, literal offsets and Boolean guards. It does not
handle arbitrary loops, cross-bit writes, general overflow or signed semantics.
The threshold basis is sufficient but not claimed minimal for every Boolean
predicate; the subsequent factor is minimal for its declared finite consumer.
Limits are eight interval values, sixteen suffix actions and sixty-four
residual states in the complete factor chain. Budget exhaustion returns no
certificate. Full Java correctness and new Lean results are outside this step.

## Independently supplied masked-upper properties

The [property report](PROPERTY_REPORT_RU.md) adds a target check after source
observation inference. A source-model certificate now reports
`claim: source_model_equivalence`; it does not by itself establish that the
program meets a user's specification.

The caller supplies a separate versioned specification: either a legal output
within the bound, or the maximum legal output within that bound. Legal words
are `seed | s`, where `s` ranges over subsets of the optional mask. The contract
requires disjoint seed/optional masks and `seed <= bound`. Inputs with no
feasible word are outside this property; no emptiness verdict is inferred.

The checker verifies a closed joint observation of the source factor and four
word-order questions. A separately quantified legal alternative detects a
non-maximal result. Every input column is checked, so induction covers every
positive payload width of the restricted mathematical source model. The source
frontend and word-split rules remain trusted; there is no new all-width JVM or
Lean result. The target vocabulary is a supported contract with explicit order
rules, not a general specification-language inference engine.

| Source condition | Maximum legal output | Legal output within bound |
|---|---|---|
| `trial <= bound` | Certified: 49 joint states, 980 transitions | Certified |
| `trial <= bound + 1` | Refuted: output exceeds bound | Refuted |
| `trial < bound` | Refuted: a better legal output exists | Certified |
| `trial <= initialValue` | Refuted: a better legal output exists | Certified |

All four sources still have valid source-model certificates. A valid refutation
is checked against the source factor, direct integer execution and an independent
integer evaluation of the target. Source, source certificate and the separately
supplied specification are bound together; merely rehashing a weaker goal does
not bypass the protected target checks.

```sh
python -m research.observations.run_property_experiment reproduction/property --native
python -O -m research.observations.property_cli check reproduction/property/original.java --source-certificate reproduction/property/original.source_certificate.json --spec reproduction/property/maximum.spec.json --certificate reproduction/property/original.maximum.certificate.json
```

To create a target template use `python -m research.observations.property_cli spec
maximum.spec.json`; `--claim bound` selects the weaker target. Use `derive` with
the same source/model/specification arguments and a new certificate path to
produce a property package. Replay needs no native Java, source producer or SMT.
CLI exit codes are 0 for a certified property, 1 for a checked refutation, 2 for
an exhausted producer budget and 3 for a rejected input or certificate. Existing
files are preserved. Positive certificates and refutations use distinct kinds.

`evidence/property/` retains all sources, source certificates, both independent
targets, eight property results and validation data. At widths 1–3, the experiment
executes all 2,954 disjoint raw parameter inputs for each of four variants, rather
than just one representative per source column. Of these, 1,859 per variant meet
the additional nonempty-domain precondition. In total 11,816 native helper calls
and 17,472 comparisons with legal alternatives agree with the observations.

## Earlier evidence

`evidence/` contains newly derived certificates for the original carry cell, a
semantically changed cell, a delayed-observation example and an unobserved-state
control. A certified quotient of the changed cell does **not** certify its
correctness as a masked successor: it faithfully represents that changed model.

The tests include 120 deterministic finite models compared against an independent
product-state equivalence oracle; 40 state/order renamings; native variable
renaming; poisoned old quotient code; 15 certificate mutations; source changes
including a forged replacement hash; normal and optimized fresh-process replay
with producer/SMT imports blocked; and 341 native/quotient trace comparisons.
