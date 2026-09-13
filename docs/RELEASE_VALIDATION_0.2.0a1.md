# Candidate validation, 13 September 2026

These are new local checks of the prepared 0.2.0a1 source tree. Full logs and
machine-readable outcomes are in `validation/release_0.2.0a1/` at repository root.

| Check | Result |
|---|---|
| Python suite | 67 passed on Python 3.12 / Linux |
| Ruff lint / format | Passed |
| Wheel and sdist | Built successfully; research/papers excluded from Python distributions |
| Wheel installed outside checkout | XOR certified, optimal, all positive widths |
| Research KnownBits replay | All 39 cases checked; 11 whole proofs, 104/411 components; no producer/SMT modules loaded |
| Graal saved proof chain | Seven fresh proof processes passed |
| Lean 4.33.0 | Fresh build completed, 13 jobs, including expected-axiom audit |
| Paper III v2 | 27 pages; references resolved, no overfull boxes; embedded Type 1 fonts; page review |
| Baseline runtime comparison | Core Python files unchanged except the version constant |

Commands follow `RELEASING.md` and `research/README.md`. This managed environment
used local development dependencies and its official Lean SDK. A small runtime
adapter resolved the current executable path where procfs is unavailable; it did
not alter Lean proof checking. The retained Lean pilot includes its adapter source
and original provenance. Standard computers need no such adapter. Standard TeX
Live needs no environment-specific font-map setup.

The independent source-hash and certificate checks passed on the preserved
research capsules. Data expansion is reversible and lossless; the published source
asset includes its packed data, not the expanded 488 MB of JSON.

The original native Java, SMT, producer and Lean negative-control experiments
remain historical measurements. They were not rerun or relabeled as new release
experiments. Lean does not verify full Python/Java or full Graal create.

GitHub connection was confirmed, but no callable GitHub write commands were
exposed in the preparation session. No remote branch, PR, tag or release was
created. The release kit includes the exact patch and draft instructions. Remote
CI on the final uploaded commit is still required before publication; local checks
do not assert a GitHub Actions result.
