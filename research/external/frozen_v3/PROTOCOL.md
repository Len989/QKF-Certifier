# Frozen v3: baseline and prospective external evaluation protocol v1

## 0. State at PR #26

**Engine and rules are frozen; no new corpus is registered or executed here.**
`REGISTRATION.json` deliberately has `corpus: null` and
`first_holdout_execution: null`. There is no holdout runner, downloader,
`CORPUS.json`, or new coverage result in this directory. Existing CI may rerun
old development/regression populations; those are not this evaluation.

This protocol implements Block A of `docs/QKF_ROADMAP_v0.1_RU.md`. Its purpose is
to measure the starting point before connecting signed inference to the existing
observation/forced-row kernel, not to redefine QKF as a coverage-only project.

## 1. Freeze and execution gates

1. **Engine/rules gate (this PR).** Publish ENGINE, this protocol, the roadmap,
   mechanism map and their byte seals. Baseline is main after merged PR #25,
   `c8c7b4eeaf848d31c8c324a4316ffec8aac81cda`, tree
   `4838b8badbb3a56f8a7d2a197ce6c0d3d6b3a77d`.
2. **Acquisition gate (next PR, before reading candidate bodies).** Commit an
   ordered repository pool, exact revisions, the reason for each selection,
   method/file selection procedure and previous-exposure ledger. Do not query
   QKF, its source frontend, a solver, or native implementations to select items.
   Already inspected candidates cannot be relabelled blind; log the exposure.
3. **Corpus gate (separate published commit before any evaluation).** Commit
   all source blob/SHA-256 identities, complete method denominator, documented
   contracts, independent goals or explicit missing-goal reasons, license
   provenance, extraction/runner code and exact runtime versions. Record the
   preceding gate commit and its hashes in the new registration record.
4. **Execution gate (PR #27).** Verify every seal, every source byte and all
   baseline bytes in clean checkouts. Record the committed runner hash and UTC
   start before attempting any method. Only then execute the measured pipeline.

The acquisition and corpus commits must be visible in Git history, not fabricated
as retrospective timestamps. Do not squash away the gate history. A corpus
cannot be called preregistered merely because its JSON was written before its
SUMMARY in the same uncommitted working directory. Until gates 2 and 3 exist,
`python -m research.external.frozen_v3.verify --require-corpus` exits 2.

## 2. Conservative engine identity

ENGINE locks **all 1,837 files of the accepted repository snapshot**, not an
optimistically inferred list of imports. The snapshot includes producers,
checkers, frontends, delegated legacy routes, data, tests, historical capsules,
paper sources and environment declarations. Git tree hashing covers names,
bytes and executable modes. A canonical sorted inventory of path/mode/size and
per-file SHA-256 supplies a second digest; count and total byte size are checked.
This superset covers dependencies without claiming all files participate in
all proofs. Individual imports are not a substitute for the full snapshot lock.

The validator permits only this new registration directory, two explicitly named
documents and one explicitly named workflow outside the baseline. Disposable
root build/output directories and Python caches are omitted from hashing. These
exclusions **are not an execution sandbox**. For evaluation export the exact
baseline to a fresh directory, run without pre-existing caches or installed
editable QKF copies, disable bytecode writing, and put generated outputs and
runner code outside the baseline. Record interpreter, platform, environment,
import search path, actual loaded local module paths, and pre/post snapshot IDs.
Import neither holdout-controlled code nor a second checkout as QKF modules.
The runner must not monkeypatch frozen modules or change module constants.

The registration utility is metadata verification, not a proof checker. A digest
binds bytes; it does not prove Java correspondence or mathematical correctness.
Changing the manifest and verifier together produces a new registration, not a
validation of the original one. Historical frozen_v1/v2 and all old evidence are
included verbatim; frozen_v2's 1/15 is never recalculated by this PR.

## 3. Acquisition, denominator and leakage

Before candidate bodies are inspected, the acquisition gate must enumerate at
least three independent public repositories not previously used as QKF
source-development populations. Repository choice is human metadata-only
selection, not a claim of random sampling from all Java. Record forks, copied
utility families, licenses and every known prior exposure. Use immutable Git
revisions, never moving branches, as the source of truth.

For each pinned tree, enumerate all production `.java` files outside paths with
segments `test`, `tests`, `benchmark`, `benchmarks`, `example`, `examples`,
`generated`, `build`, `target`, `vendor`, or `third_party` (case-insensitive).
The candidate file frame is every remaining file whose basename contains
`bit` or `math` (case-insensitive). Preserve that complete path frame and all
exclusion reasons. This is a declared bit/math utility stratum, not general
Java coverage. No one may replace a repository or file after finding that its
methods are unsupported or inconvenient. Empty contributions stay recorded.

Read declarations with an independent lexical/declaration inventory, not QKF's
accepted-source parser. The denominator is **every explicitly public static
method with exactly one primitive int/long parameter and return type boolean,
int or long** in this complete file frame, including nested classes and
unsupported bodies. Overloads are distinguished by qualified class, signature
and source span. Varargs, arrays, generic/reference parameters and constructors
are out by syntax, not by implementation success. Annotation/comment stripping
must preserve source-span provenance; unclear declarations require logged review,
not silent omission. Retain exception-throwing and side-effecting bodies too.

There is no success-conditioned quota or replacement sampling. If this frame is
infeasible, amend and version the acquisition protocol **before execution** and
record all already inspected material; do not retrospectively call it blind.
Exact raw blob duplicates and normalized body clones are assigned clone-group
IDs before execution. Normalize whitespace/comments and parameter/local names
only for clone diagnostics, never modify the actual evaluated source. All
syntactically eligible methods remain in the raw denominator. Separately report
unexposed methods and clone groups; known previously used implementations are
labelled exposed/reference, not independent novelty. Do not infer independence
just from a different library or method name.

## 4. Independent target registration

For every denominator method register its documented full contract with a pinned
Javadoc/documentation source and source span. Record signedness, physical Java
width, zero behavior, overflow, exceptional inputs and preconditions. A contract
with no clear independent documentation is `contract_unavailable`, not an
opportunity to synthesize a target by copying the implementation.

Register a QKF goal only if the **unchanged** supported target grammar expresses
the actual obligation and preconditions. Do not discard exceptions, restrict
inputs after seeing witnesses, strengthen a guarded claim, or replace the
positive-power-of-two contract by popcount=1. The sign-bit-only negative value
separates those properties. A documented physical-width contract and its chosen
all-positive-width mathematical extension must both be explicit; the latter is
not silently attributed to upstream documentation.

Where a faithful goal is unavailable, retain the method with
`no_supported_target_language` and a reason. QKF success cannot determine target
choice. A `word_result` int method is not silently widened to long. Legacy
masked-bound delegation and ascending-region semantics, if used in a separate
reference track, keep their own identifiers and do not count as unary v3 gain.
The default registered inference budgets are exactly ENGINE's 128 selected
features and 8192 target states; inherited route-specific caps stay unchanged.

## 5. Result taxonomy and accounting

Retain raw stdout/stderr, exit code and original engine result separately from
the evaluation classification. The wrapper may add stage and resource metadata,
not turn a failure into a proof. Every denominator method gets a record.

- `certified`: independent source-bound replay accepts the registered goal.
- `refuted`: a replayed source-bound witness violates that same goal at its final
  width. A small-width witness is not automatically an upstream Java bug.
- `unsupported`: preserve `no_source_profile`, `source_unsupported`, or
  `no_supported_target_language` as a separate reason/stage.
- `budget_exhausted`: record feature/model/product cap, wall timeout or memory
  cap distinctly; no certificate of impossibility is inferred.
- `contract_unavailable`: no defensible independent obligation registered.
- `input_error`, `internal_error`, `invalid_certificate`, missing input,
  failed hash/identity check and infrastructure failure: retain the case and fail
  complete experiment acceptance. They are not refutations or invisible rows.

A stage not executed is `not_attempted`, not guessed from the method name.
Non-proof applicability diagnostics may run only after the execution gate and
must not influence the frozen denominator or goal. Accept an experiment only
when all registered records exist, all claimed proof results replay, all seals
hold, and no unaccounted infrastructure/internal failure remains. Partial output
may be published but must be labelled incomplete; do not drop its failures.

Report raw all-method coverage, documented-goal coverage and route support
separately, always with denominators. Report clone-group and exposure breakdowns.
Do not add per-version repetitions, components or native samples to method counts.

## 6. Cost, runtime and repeatability

Use ENGINE's Linux x86_64, Python 3.10/3.12 and Java 17 matrix. Pin actual Python,
JDK, OS/container versions and runner revision at the corpus gate. Major/minor
selectors in CI are not exact binary pinning. Python 3.12 is the primary timing
track; Python 3.10 is cross-version verification, not a second independent corpus.

Each method runs in a fresh process, without parallel competing measurements:
one discovery attempt (120 seconds, 2 GiB address-space ceiling), followed by
three fresh replay runs on any accepted proof (120 seconds each, same memory
ceiling). Discovery includes its built-in checker; report separately measured
replay and median/range, not an invented exclusive search time. Collect wall
and CPU time, child-process peak RSS where supported, counts, proof bytes and all
failed attempts. Any missing resource metric stays null with an explanation.
Acquisition and compilation have separate accounting. OS-enforced memory failure
must be identified from supervisor evidence; arbitrary nonzero exit is not OOM.

Replay blocks producer and solver imports before checker load, and blocks native
execution. Compare canonical proof/result content between versions, recording
irrelevant log timing differences separately. Any differing verdict or proof
identity must be investigated and retained, not selected by the favorable run.

## 7. Native validation and comparison with v2

Use physical 32/64-bit Java only. For executable pure accepted methods compile
the exact selected declarations in isolated harnesses with `--release 17`,
retaining source spans and a description of removed compile-only annotations.
No replacement implementation is allowed. Missing dependencies or side effects
remain explicit native-validation limitations. Compile budget: 60 seconds;
execution budget: 120 seconds. Native execution is never part of proof replay.

At width w, build a deterministic set from 0..65535 reduced modulo 2^w,
all-ones, min/max signed words, and values 2^i-1, 2^i, 2^i+1 modulo 2^w for
0<=i<w. Add 4096 values formed by the first w/8 bytes (big-endian) of
SHA-256(UTF-8("qkf-frozen-v3-native:" + canonical_case_id + ":" + decimal_index))
for indices 0..4095, plus all reported physical-width witness candidates.
Deduplicate and sort by raw unsigned value. Convert to signed values only when
calling Java. Compare separately to the whole-word source IR and the independently
registered target. Preserve throws rather than substituting Boolean/numeric values.
Count finite inputs and disagreements separately from universal proof coverage.

Paired v2 comparison is optional only if committed at the corpus gate. Run the
unchanged old engine on the same obligation and input bytes where expressible;
missing signed target support stays a capability gap. Do not compare different
goals under a shared success label. Do not claim improvement from percentages
on different corpora. This protocol introduces no SMT performance comparison.

## 8. No tuning and future reuse

After the execution gate do not alter source selection, targets, engine bytes,
route choice, budgets, clone/exposure labels or acceptance rules. Record the first
attempt even if it fails. Infrastructure-only re-execution requires an incident
record and identical frozen inputs; keep all attempts and resource accounting.
A semantic or checker defect invalidates affected claims. Repair it in a separately
versioned development engine; report invalidation rather than quietly regenerating
a successful baseline.

After examining this corpus to develop v4, it is a reference/development population
for v4. A fresh v4 evaluation needs a new engine freeze and a new unexposed corpus.
Prior historical results, including v2 1/15, retain their original meaning.

## 9. What this registration does not claim

No new theorem, new Java/source profile, new observations, general synthesis of
observation languages, speedup, new Lean coverage or new holdout result is added.
The general observation kernel and atomic row representation already exist.
The next engineering bridge is separately scheduled in PRs #28–31.

Verification of metadata here cannot prove that no private experiment ever took
place. It provides committed prospective rules, byte identities, fail-closed
readiness and a public execution record requirement. Exposure must also be
reported honestly by the experimenter.
