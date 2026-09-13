# Research and Lean profiles

This directory makes the later QKF work reproducible alongside the Python coordinatewise CLI. The profiles have separate source contracts, certificate formats, and implementation boundaries.

| Profile | What is checked | Entry point |
|---|---|---|
| knownbits/ | Original 39-program corpus: 11 whole proofs, 104/411 component proofs | Repository research runner |
| graal/ | Universal upper and conditional lower contracts, with their saved proof chain | Repository research runner |
| lean/ | Formal rows, carry quotient, gluing and numerical successor model | lake build in that directory |

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

```sh
python -m research.observations carry reproduction/observations_carry
python -m research.observations check-carry reproduction/observations_carry/certificate.json
```
