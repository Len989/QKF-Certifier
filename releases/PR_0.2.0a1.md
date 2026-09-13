## Why

The public repository and Paper III still describe the coordinatewise 0.1.0a1
stage. The later observation and signed-word proofs, their limitations and the
Lean pilot need a reproducible, explicitly scoped home.

## Changes

Prepare 0.2.0a1 with manuscript 2.0, frozen KnownBits/Graal research capsules,
a separate replay runner, the Lean 4.33.0 project, claim/provenance maps and
research CI. Preserve the prior paper and its evidence. Keep runtime core
semantics and the qkf-rewrite-v3 format unchanged.

Broader research is launched separately from the installed AND/OR/XOR CLI.
Whole-program coverage is 11/39, component coverage 104/411; upper/lower helper
theorems do not establish full Graal create correctness. Lean checks the stated
ascending model and source cells, not all Python/Java.

## Validation

The included candidate record covers 67 Python tests, all 39 KnownBits replays,
seven fresh Graal proof processes, a clean 13-job Lean build, lint, distributions,
installed-wheel verification and the 27-page manuscript. Confirm both GitHub
workflows on this PR's final commit before publication.

Keep the release a draft pre-release until review. No PyPI/DOI publication is part
of this change.
