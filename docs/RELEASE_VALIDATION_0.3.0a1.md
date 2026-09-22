# Candidate validation, 22 September 2026

This record distinguishes fresh local checks of the 0.3.0a1 release preparation
from checks of the accepted research baseline. The preparation base is
`eca90f9252da4480d77c1f8cb4b7062470c57b89` (the merge of PR51). It is not a
claim about the eventual release tag or commit. Logs and machine-readable results
are included in the release preparation evidence under `evidence/validation/`.

| Check | Scope and result |
|---|---|
| Python package suite | Release tree, Python 3.12.14: 67 tests, zero failures/errors/skips, confirmed by JUnit XML |
| Ruff lint and format | Release tree: passed; 64 files already formatted |
| Ground-query and SDK comparison unit tests | Release tree: 77 tests passed |
| Wheel and sdist | Built as 0.3.0a1 with local build dependencies; research, formal, papers and reproduction trees excluded |
| Installed wheel | Clean virtual environment outside checkout; distribution/runtime version 0.3.0a1; XOR certified and optimal for all positive widths |
| Formal Python adapters and integrity guards | Immutable accepted baseline: 45 tests passed, repeated under `python -O` with 45 passed |
| Formal adapter suite on release tree | 43 tests passed, two historical whole-tree preservation guards rejected changed release documentation; identical outcome under `python -O` |
| Release delta | Exact baseline byte/mode audit: all 2073 research/formal/test/example/workflow/tool files preserved; package runtime changes only its version string |
| Manuscript | 37-page Paper III v3.0; final LaTeX passes without warnings or box overflows; embedded fonts, all-page visual review and independent claim/number review passed |
| Local Lean compilation | Not rerun: neither `lake` nor `lean` is installed in this environment |

The package's randomized normalization property ran 500 passing examples. Wheel
verification used the repository's frozen XOR and meet MLIR inputs and reported
`compiler_lowering_verified: false`, preserving the published semantic boundary.
No new package behavior is asserted by changing its version number.

## Historical preservation guards

The formal PR50 guard compares every accepted PR49 file against its original Git
blob; PR51 does the same against PR50. They deliberately include metadata, papers,
and release documentation. The first release-tree mismatch is `CHANGELOG.md`.
That is an expected documentation difference, but the two tests still return
errors; they are not counted as successful release-tree tests. Neither the guards
nor their historical exception lists have been weakened for this release.

Both complete formal adapter suites were therefore rerun in a separate clean
worktree at the preparation base, where all 45 tests pass in each Python mode.
These runs validate the unchanged accepted formal adapter implementation and its
historical invariants. They do not claim to execute Lean, validate a new commit's
remote CI, or turn release documentation changes into an additive PR50/51 tree.

## Reproduction and remaining publication gates

Commands are in `docs/RELEASING.md`. The local package build used an isolated
workspace virtual environment and `python -m build --no-isolation`; its build
dependencies were installed explicitly. The installed-wheel smoke test used a
second virtual environment, with no editable source installation and no checkout
on its import path. `distributions.json` records the inspected archive contents;
asset checksum files record the final distributable bytes.

The full historical experiments and timing comparisons were not rerun for this
packaging update. Recorded research and Lean CI belongs to its stated original
commits. The release tree needs its own required CI before publication. The separate
`RELEASE_DELTA.json` comparison explicitly allows only the enumerated publication
files and version-only metadata edits while checking the protected scientific
implementation byte for byte. It does not relax any historical guard.
No GitHub publication, new DOI assignment, or PyPI upload is asserted here.
