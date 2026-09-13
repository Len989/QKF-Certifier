# Preparing and publishing QKF Certifier 0.2.0a1

Repository: [Len989/QKF-Certifier](https://github.com/Len989/QKF-Certifier).
Candidate: **0.2.0a1**, tag **v0.2.0a1**, manuscript **2.0**. Keep this a pre-release.
The intended preparation branch is `release/0.2.0a1`.

## Validate the complete candidate

On Linux with Python 3.12, from a full checkout:

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m build
python tools/replay_research.py --suite all --output reproduction/release_01
cd research/lean
lake build
```

Also install the wheel in a clean environment outside the checkout and check the
packaged example. Review the paper PDF and its source/claim mapping. The manuscript
build instructions are in `papers/paper_III/SOURCE_README.md`.

The wheel/sdist contain the coordinatewise CLI. The complete research source asset
contains research capsules, the papers and Lean sources. Restored KnownBits JSON,
Lean build caches, local dependency installations and TeX build files are excluded
from the source asset. The packed research data and all original evidence hashes
must remain present.

## Prepare the GitHub draft

1. Start from the recorded baseline or review changes if `main` has moved. Create
   `release/0.2.0a1`, commit the prepared changes, and push that branch normally.
2. Open a draft PR against `main`. Use `releases/PR_0.2.0a1.md` as its description.
3. Check **Test and build** and **Research and Lean** on that exact commit. The
   earlier 0.1.0a1 successful run is historical evidence, not this release's gate.
4. Create a **draft**, **pre-release** targeting that commit, titled
   `QKF Certifier 0.2.0a1 — observations and word proofs`, using
   `releases/v0.2.0a1.md`. Attach the PDF, LaTeX archive, complete research source
   archive, wheel, sdist and SHA-256 asset manifest.
5. Leave the PR and release in draft for review. If code or documentation changes,
   rebuild assets, refresh hashes, and use checks for the new commit. The release
   kit includes exact commands for creating this draft through GitHub CLI.

## Publication after review

Merge only the reviewed changes. Identify the exact reviewed commit in the release
record, confirm its own CI, then publish the draft at that commit. If the merge
changes the tree, regenerate and revalidate affected assets. Keep the prior release
and Paper III v1. No workflow here publishes to PyPI or deposits a manuscript.
The author chooses the manuscript license and DOI deposit separately; the prepared
citation must not invent either.

## Historical first release

Public v0.1.0a1 points to `f93561682319e8b911ed32c01583f2a496dc59fc`.
Its first complete upload passed the original eight CI jobs at
`4beeb5b5399909dc9abb7da25acec2d8704657bf`:
[recorded run](https://github.com/Len989/QKF-Certifier/actions/runs/34636148287).
`LOCAL_VALIDATION.md` and the v1 paper supplement retain those earlier records.
