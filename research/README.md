# Research and Lean profiles

This directory makes the later QKF work reproducible alongside the Python coordinatewise CLI. The profiles have separate source contracts, certificate formats, and implementation boundaries.

| Profile | What is checked | Entry point |
|---|---|---|
| knownbits/ | Original 39-program corpus: 11 whole proofs, 104/411 component proofs | Repository research runner |
| graal/ | Universal upper and conditional lower contracts, with their saved proof chain | Repository research runner |
| lean/ | Formal rows, carry quotient, gluing and numerical successor model | lake build in that directory |
| observations/ | Source-derived factors; independent descending maximum and ascending cyclic successor goals | Research CLIs and saved-evidence replay below |

Use Python 3.12 on Linux/POSIX, without -O. From the repository root:

```sh
python tools/replay_research.py --suite all --output reproduction/run_01
```

The output directory must be new. The runner checks retained bytes, restores losslessly packed KnownBits data, and replays proofs in fresh processes with the original producer/SMT blockers. Restoring data expands roughly half a gigabyte of repetitive JSON; the archive is much smaller. No solver or Java installation is needed for replay.

For a smaller first check:

```sh
python tools/replay_research.py --suite knownbits --case KnownBits_Add --output reproduction/add_01
python tools/replay_research.py --suite graal --output reproduction/graal_01
```

Historical archive-chain restore commands inside the preserved directories belong to their original handoff packages. Use this release runner for these publication capsules; the old nested handoff archives are not needed.

For Lean, install the official Lean 4 toolchain manager, then:

```sh
cd research/lean
lake build
```

Lean selects version 4.33.0 from lean-toolchain. Python, Mathlib, SMT and Java are not required for this build. Full instructions are in the Lean directory.

The Lean proof covers the explicit ascending mathematical model and modeled nonsign source cells. Complete Java helpers, full Graal create and Python certifiers are outside that formalization. The lower source contract requires lower <= 0 or a forbidden negative sign; it preserves the joint carrier and need not return its exact minimum.

CAPSULE_ORIGIN.json records unchanged files in each Python profile. QKF research code is covered by the project MIT code license. Upstream sources and examples retain their own notices and licenses.

## Automatic observation inference (post-release research)

The [observation inference prototype](observations/README.md) derives a finite
consumer interface directly from the existing native carry cell, without its
hand-written phase quotient. It emits replayable observation and forced-row
certificates, including separating contexts. This is new research after 0.2.0a1;
it does not extend the installed CLI scope or the signed-word theorem.

The same profile now also derives the residual shared-context observation for
the descending comparison model and finds a two-bit counterexample to forgetting
its cut constraints. See the [shared-context report](observations/CONTEXT_REPORT_RU.md).
The [consumer-factor extension](observations/FACTOR_REPORT_RU.md) now reduces
those 15 residual states to 10 minimal classes, using compact forced-row
certificates and a checker for the complete source-to-factor chain.

The [source observation extension](observations/SOURCE_REPORT_RU.md) now derives
the initial integer questions and shared slices from the actual descending
Java helper. For guards with offsets 0, +1 and +3 it discovers 3, 4 and 6
context values, then 10, 13 and 20 minimal factor classes. Shared input identity
is also extracted from the code. The exact arithmetic certificate covers a
restricted unsigned mathematical word profile; the Java connection is tested
at payload widths 1–5, not proved for all signed machine words.

The [independent property stage](observations/PROPERTY_REPORT_RU.md) checks a
separately supplied maximum/bound specification after source inference. The
original helper satisfies the maximum contract in the restricted mathematical
profile; `bound + 1` yields an above-bound counterexample, while a strict guard
preserves the bound but loses maximality. Source-model equivalence and target
correctness are reported as separate claims.

The [ascending source stage](observations/ASCENDING_REPORT_RU.md) derives
Boolean-register and integer-offset states from the actual repair loop, using
shared parsing and observation kernels. No old carry cell or prescribed phase
table is used. Five source variants agree with 28,105 JVM executions of the
extracted region. That source certificate covers all positive mathematical
payload widths under a legal-mask entry contract; it does not by itself prove
an independent successor goal or the surrounding helper control flow.

The [independent successor stage](observations/SUCCESSOR_REPORT_RU.md) now connects
that source-derived factor to a separately supplied cyclic-successor target.
The original and irrelevant-register variants have an 8-state / 48-transition
closed-observation certificate for every positive mathematical payload width.
Three behavior-changing variants have checked integer counterexamples while
still satisfying the weaker mask-membership target. The new schema does not
certify whole-helper control flow, full signed Java returns or a new Lean theorem.
Ten [retained property packages](observations/evidence/successor/README.md) replay
without producer search, SMT or native Java, including under Python -O:

```sh
python -O -m research.observations.replay_successor_evidence
python -m research.observations.run_successor_experiment reproduction/successor_01
```

These observation entry points require Python 3.10+ and are separate from the
publication-capsule runner above and the installed public package. Add `--native`
to the experiment for bounded Java 17+ validation. Per-source target checking is
available through `python -m research.observations.successor_cli --help`.

```sh
python -m research.observations carry reproduction/observations_carry
python -m research.observations check-carry reproduction/observations_carry/certificate.json
```
