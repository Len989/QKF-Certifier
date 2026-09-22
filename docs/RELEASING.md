# Preparing and publishing QKF Certifier 0.3.0a1

Repository: [Len989/QKF-Certifier](https://github.com/Len989/QKF-Certifier).
Candidate: **0.3.0a1**, proposed tag **v0.3.0a1**, Paper III **3.0**.
Keep this an alpha pre-release. The preparation branch is `release/0.3.0a1`.
The preparation date is 22 September 2026; it is not a publication date.

## Validate the complete candidate

On Linux with Python 3.12, from a full checkout:

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m build
python tools/replay_research.py --suite all --output reproduction/release_0.3.0a1
```

Build the pinned Lean projects with their recorded toolchains:

```sh
(cd research/lean && lake build)
(cd research/lean_targets && lake build)
(cd formal/ground && lake build)
(cd formal/composition && lake build)
```

Run the historical formal adapter/integrity suites on the exact accepted
research baseline, whose research/formal source bytes the release delta preserves:

```sh
git worktree add --detach ../qkf-accepted-pr51 eca90f9252da4480d77c1f8cb4b7062470c57b89
cd ../qkf-accepted-pr51
python -m unittest formal.ground.test_export formal.composition.test_export -v
python -O -m unittest formal.ground.test_export formal.composition.test_export -v
```

The formal clean-tree audits preserve historical baselines. Release documentation,
metadata, and paper additions can change files outside each original exception
list. Review any such failures against the release diff; do not weaken an audit or
relabel the original PR's successful CI as CI for a new release commit.

Install the wheel in a clean environment outside the checkout and verify the
packaged CLI with `examples/ntmy/xor.mlir` and its `meet.mlir` helper. Confirm that
the installed distribution and `qkf_certifier.__version__` both report `0.3.0a1`.
Review Paper III's PDF, source/claim mapping and source archive. Build instructions
are in `papers/paper_III/SOURCE_README.md`.

The wheel and sdist contain the coordinatewise KnownBits package. Separate research
and formal sources are distributed in the complete source archive. The packaged
CLI does not silently acquire every feature demonstrated by a research capsule.
Exclude local dependency installations, build caches, expanded research datasets,
and TeX intermediate files; retain packed data and original evidence manifests.

## Prepare the GitHub release

1. Review the prepared diff against its recorded base. Commit and push
   `release/0.3.0a1` normally. Use `releases/PR_0.3.0a1.md` for the PR description.
2. Run the five branch-push workflows on the exact candidate commit: **Test and
   build**, **Research and Lean**, **Unified research run**, **Composed masked
   ceiling**, and **Typed targets and Lean integration**. The kit publication
   helper checks their exact head and all other triggered push outcomes. Keep
   the accepted formal/current-research CI and the unchanged-code delta evidence
   separate. A PR additionally runs historical whole-tree preservation guards;
   review their release-documentation policy explicitly if using that route.
   Do not weaken a required check or call historical results fresh release CI.
3. Create a draft pre-release with proposed tag `v0.3.0a1`, targeting the exact
   reviewed commit. Use `releases/v0.3.0a1.md` as its release notes.
4. Attach the current Paper III PDF, LaTeX source archive, complete source archive,
   wheel, sdist, and SHA-256 asset checksums. Preserve prior paper and release assets.
5. Rebuild the distributions after any packaged document or metadata change.
   Refresh `RELEASE_MANIFEST.json` after the final content edits, excluding that
   manifest itself and generated caches. Its preparation base is not the eventual
   release commit. Recompute asset checksums last.

## Publication and manuscript deposit

Publish only the reviewed tree with its own release validation. If a merge changes
the tree, regenerate and validate affected assets. A draft record, proposed tag,
local build, or historical CI result is not a published release.

Paper III v3.0 is a new manuscript version. Preserve the existing Zenodo record and
upload through its new-version flow. Do not fabricate a version DOI, publication
date, tag target, or release commit in citation metadata. Record an actual assigned
DOI and publication date after the deposit. This workflow does not publish to PyPI.

## Historical records

`docs/RELEASE_VALIDATION_0.2.0a1.md`, `docs/LOCAL_VALIDATION.md`, and the retained
paper supplements describe their own historical candidates and checks. They are
not validation claims for version 0.3.0a1. Current local results are recorded in
`docs/RELEASE_VALIDATION_0.3.0a1.md`.
